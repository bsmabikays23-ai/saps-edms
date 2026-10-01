import sqlite3
import psycopg2
from psycopg2 import sql

# ====== CONFIG ======
SQLITE_FILE = "saps_edms.db"  # SQLite database in this project folder
NEON_URL = "postgresql://neondb_owner:npg_Tuv0NBoImqD6@ep-soft-wave-b5wk5z4z.c-7.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"  # <-- paste your real string
# ====================

def convert_type(sqlite_type):
    """Map SQLite types to Postgres types."""
    t = (sqlite_type or "").upper()
    if "INT" in t:
        return "BIGINT"
    if "CHAR" in t or "CLOB" in t or "TEXT" in t:
        return "TEXT"
    if "BLOB" in t:
        return "BYTEA"
    if "REAL" in t or "FLOA" in t or "DOUB" in t:
        return "DOUBLE PRECISION"
    if "DATE" in t or "TIME" in t:
        return "TIMESTAMP"
    if "BOOL" in t:
        return "BOOLEAN"
    return "TEXT"


def fix_value(value, pg_type):
    """Convert a single value from SQLite to something Postgres accepts."""
    if value is None:
        return None

    if pg_type == "BOOLEAN":
        # SQLite stores booleans as 0/1
        return bool(value)

    if pg_type == "BYTEA":
        # psycopg2 wants bytes
        if isinstance(value, memoryview):
            return bytes(value)
        return value

    if pg_type == "TIMESTAMP":
        # SQLite may store dates as strings; leave them for now
        return value

    return value


def migrate():
    # Connect to SQLite
    sqlite_conn = sqlite3.connect(SQLITE_FILE)
    sqlite_cur = sqlite_conn.cursor()

    # Connect to Neon
    pg_conn = psycopg2.connect(NEON_URL)
    pg_cur = pg_conn.cursor()

    # Get all user tables from SQLite
    sqlite_cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    )
    tables = [row[0] for row in sqlite_cur.fetchall()]

    for table in tables:
        print(f"\n>>> Migrating table: {table}")

        # Get column info
        sqlite_cur.execute(f'PRAGMA table_info("{table}");')
        columns = sqlite_cur.fetchall()
        # columns = [(cid, name, type, notnull, dflt_value, pk), ...]

        col_defs = []
        col_names = []
        col_pg_types = []

        for col in columns:
            cid, name, ctype, notnull, default, pk = col
            pg_type = convert_type(ctype)
            col_names.append(name)
            col_pg_types.append(pg_type)

            if pk:
                col_defs.append(f'"{name}" {pg_type} PRIMARY KEY')
            else:
                null_clause = " NOT NULL" if notnull else ""
                col_defs.append(f'"{name}" {pg_type}{null_clause}')

        # Drop & recreate table in Postgres (fresh start)
        pg_cur.execute(
            sql.SQL("DROP TABLE IF EXISTS {} CASCADE;").format(
                sql.Identifier(table)
            )
        )
        create_sql = f'CREATE TABLE "{table}" ({", ".join(col_defs)});'
        print(f"    {create_sql}")
        pg_cur.execute(create_sql)

        # Fetch all rows from SQLite
        sqlite_cur.execute(f'SELECT * FROM "{table}";')
        rows = sqlite_cur.fetchall()

        if rows:
            # Convert each value according to its target Postgres type
            fixed_rows = [
                tuple(
                    fix_value(value, col_pg_types[i])
                    for i, value in enumerate(row)
                )
                for row in rows
            ]

            placeholders = ", ".join(["%s"] * len(col_names))
            quoted_cols = ", ".join([f'"{c}"' for c in col_names])
            insert_sql = (
                f'INSERT INTO "{table}" ({quoted_cols}) '
                f"VALUES ({placeholders});"
            )
            pg_cur.executemany(insert_sql, fixed_rows)
            print(f"    Inserted {len(fixed_rows)} rows.")

        pg_conn.commit()

    print("\n✅ Migration complete!")
    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    migrate()