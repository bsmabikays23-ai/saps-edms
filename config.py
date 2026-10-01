"""
config.py — Central configuration for SAPS eDMS.
"""

import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key, default=None):
    return os.environ.get(key, default)


def _bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _int(key, default):
    try:
        return int(os.environ.get(key, str(default)))
    except (TypeError, ValueError):
        return default


class Config:
    ENV = _env("FLASK_ENV", "production")
    DEBUG = ENV == "development"
    SECRET_KEY = _env("FLASK_SECRET_KEY", "dev-secret-key-change-me")

    JWT_SECRET_KEY = _env("SAPS_JWT_SECRET", "dev-jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES_HOURS = _int("JWT_EXPIRES_HOURS", 8)

    _db_url = _env("DATABASE_URL", "sqlite:///saps_edms.db")
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    if _db_url.startswith("sqlite:///") and not _db_url.startswith("sqlite:////"):
        _db_file = _db_url.replace("sqlite:///", "", 1)
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{(BASE_DIR / _db_file).as_posix()}"
    else:
        SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    MAIL_SERVER = _env("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _int("MAIL_PORT", 587)
    MAIL_USE_TLS = _bool("MAIL_USE_TLS", True)
    MAIL_USE_SSL = _bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = _env("MAIL_USERNAME", "")
    MAIL_PASSWORD = _env("MAIL_PASSWORD", "")
    MAIL_DEFAULT_SENDER = _env("MAIL_DEFAULT_SENDER", "SAPS eDMS <no-reply@example.com>")

    UPLOAD_DIR = _env("UPLOAD_DIR", "uploads")
    MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 25)
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

    HOST = _env("HOST", "0.0.0.0")
    PORT = _int("PORT", 5000)

    LOGIN_RATE_LIMIT = _env("LOGIN_RATE_LIMIT", "5 per minute")
    RATELIMIT_STORAGE_URI = _env("RATELIMIT_STORAGE_URI", "memory://")

    BASE_DIR = BASE_DIR
    UPLOAD_PATH = BASE_DIR / UPLOAD_DIR


config = Config()