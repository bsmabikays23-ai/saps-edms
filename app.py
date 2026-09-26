"""
app.py — SAPS Electronic Docket Management System (eDMS)
Flask + SQLAlchemy + JWT + Flask-Mail + Flask-Migrate + Flask-Limiter.
Configuration is loaded from config.py (which reads .env).
"""

import os
import re
import hashlib
import uuid
from datetime import timedelta, datetime
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template, send_from_directory,
    redirect, url_for
)
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity,
    decode_token
)
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from sqlalchemy import or_

from config import config
from models import db, User, Case, Evidence, Milestone, AuditLog
from mailer import (
    init_mail, send_email, case_registered_email, milestone_email
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
UPLOAD_DIR = str(config.UPLOAD_PATH)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(config.BASE_DIR / "templates"),
    static_folder=str(config.BASE_DIR / "static"),
)

app.config["SQLALCHEMY_DATABASE_URI"] = config.SQLALCHEMY_DATABASE_URI
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = config.SECRET_KEY
app.config["JWT_SECRET_KEY"] = config.JWT_SECRET_KEY
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=config.JWT_ACCESS_TOKEN_EXPIRES_HOURS)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

ALLOWED_EXTENSIONS = {
    "pdf", "png", "jpg", "jpeg", "gif", "txt", "doc", "docx",
    "mp4", "mov", "avi", "mp3", "wav", "zip",
}

CRIME_TYPES = [
    "Housebreaking", "Theft", "Assault", "Robbery", "Fraud",
    "Murder", "Hijacking", "Drug Offence", "Other",
]

CASE_STATUSES = [
    "Open", "Under Investigation", "Awaiting Forensics",
    "Ready for Court", "Closed",
]

# Rate limit defaults
RATELIMIT_DEFAULTS = ["200 per day", "50 per hour"]

db.init_app(app)
migrate = Migrate(app, db)
jwt = JWTManager(app)
init_mail(app)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=RATELIMIT_DEFAULTS,
    storage_uri=config.RATELIMIT_STORAGE_URI,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def log_action(action, target_type=None, target_id=None, detail=None, actor=None):
    entry = AuditLog(
        actor_id=actor.id if actor else None,
        actor_label=(f"{actor.full_name} ({actor.persal_number})" if actor else None),
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()


def roles_required(*allowed_roles):
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()
        def inner(*args, **kwargs):
            user = db.session.get(User, int(get_jwt_identity()))
            if not user or not user.active:
                return jsonify({"msg": "Account inactive or missing"}), 403
            if user.role not in allowed_roles:
                return jsonify({"msg": "Insufficient privileges"}), 403
            return fn(*args, user=user, **kwargs)
        return inner
    return wrapper


def page_guard(*allowed_roles):
    def wrapper(fn):
        @wraps(fn)
        def inner(*args, **kwargs):
            token = request.args.get("token") or ""
            if not token:
                return redirect(url_for("login_page"))
            try:
                decoded = decode_token(token)
                user_id = int(decoded["sub"])
            except Exception:
                return redirect(url_for("login_page"))
            user = db.session.get(User, user_id)
            if not user or not user.active or user.role not in allowed_roles:
                return redirect(url_for("login_page"))
            return fn(*args, user=user, **kwargs)
        return inner
    return wrapper


def generate_cas_number() -> str:
    now = datetime.utcnow()
    count = Case.query.filter(
        Case.cas_number.like(f"CAS %/{now.month:02d}/{now.year}%")
    ).count() + 1
    candidate = f"CAS {count:03d}/{now.month:02d}/{now.year}"
    while Case.query.filter_by(cas_number=candidate).first():
        count += 1
        candidate = f"CAS {count:03d}/{now.month:02d}/{now.year}"
    return candidate


def pick_least_loaded_detective():
    detectives = User.query.filter_by(role="detective", active=True).all()
    if not detectives:
        return None
    def open_cases(d):
        return Case.query.filter(
            Case.detective_id == d.id, Case.status != "Closed"
        ).count()
    detectives.sort(key=open_cases)
    return detectives[0]


def apply_case_filters(query, args):
    """Apply smart-search filters to a Case query."""
    q_text = (args.get("q") or "").strip()
    if q_text:
        like = f"%{q_text}%"
        query = query.filter(or_(
            Case.cas_number.ilike(like),
            Case.complainant_name.ilike(like),
            Case.complainant_id.ilike(like),
            Case.complainant_phone.ilike(like),
            Case.complainant_email.ilike(like),
            Case.crime_type.ilike(like),
            Case.location.ilike(like),
            Case.description.ilike(like),
        ))

    crime_type = (args.get("crime_type") or "").strip()
    if crime_type and crime_type.lower() != "all":
        query = query.filter(Case.crime_type == crime_type)

    status = (args.get("status") or "").strip()
    if status and status.lower() not in ("all", ""):
        query = query.filter(Case.status == status)

    date_from = (args.get("date_from") or "").strip()
    if date_from:
        try:
            dt = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Case.created_at >= dt)
        except ValueError:
            pass

    date_to = (args.get("date_to") or "").strip()
    if date_to:
        try:
            dt = datetime.strptime(date_to, "%Y-%m-%d")
            dt = dt.replace(hour=23, minute=59, second=59)
            query = query.filter(Case.created_at <= dt)
        except ValueError:
            pass

    return query


def _validate_password(pwd: str):
    """Return None if valid, else an error message."""
    if not pwd or len(pwd) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isdigit() for c in pwd):
        return "Password must contain at least one digit."
    if not any(c.isalpha() for c in pwd):
        return "Password must contain at least one letter."
    return None


# ---------------------------------------------------------------------------
# JWT error handlers
# ---------------------------------------------------------------------------
@jwt.unauthorized_loader
def _missing(reason):   return jsonify({"msg": "Authorization required"}), 401

@jwt.invalid_token_loader
def _invalid(reason):   return jsonify({"msg": "Invalid token"}), 422

@jwt.expired_token_loader
def _expired(h, p):     return jsonify({"msg": "Token expired"}), 401


# ---------------------------------------------------------------------------
# Rate-limit error handler (with Retry-After for the client countdown)
# ---------------------------------------------------------------------------
@app.errorhandler(429)
def ratelimit_handler(e):
    retry_after = 60
    ra = getattr(e, "retry_after", None)
    if isinstance(ra, int) and ra > 0:
        retry_after = ra
    else:
        desc = str(getattr(e, "description", "") or "")
        m = re.search(r"per\s+(second|minute|hour|day)", desc, re.IGNORECASE)
        if m:
            unit = m.group(1).lower()
            retry_after = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[unit]

    resp = jsonify({
        "msg": "Too many attempts. Please wait and try again.",
        "retry_after": retry_after,
    })
    resp.headers["Retry-After"] = str(retry_after)
    return resp, 429


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/track")
def track_page():
    return render_template("track.html")


@app.route("/login")
def login_page():
    return redirect(url_for("index") + "#officerLogin")


@app.route("/csc")
@page_guard("csc", "commander")
def csc_page(user):
    return render_template("csc.html", token=request.args.get("token"),
                           user=user.to_dict(),
                           crime_types=CRIME_TYPES,
                           statuses=CASE_STATUSES)


@app.route("/detective")
@page_guard("detective", "commander")
def detective_page(user):
    return render_template("detective.html", token=request.args.get("token"),
                           user=user.to_dict(),
                           crime_types=CRIME_TYPES,
                           statuses=CASE_STATUSES)


@app.route("/detective/case/<int:case_id>")
@page_guard("detective", "commander")
def detective_case_page(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return redirect(url_for("detective_page") + f"?token={request.args.get('token','')}")
    if user.role == "detective" and case.detective_id != user.id:
        return redirect(url_for("detective_page") + f"?token={request.args.get('token','')}")
    return render_template(
        "detective_case.html",
        token=request.args.get("token"),
        user=user.to_dict(),
        case=case.to_dict(include_detail=True),
        statuses=CASE_STATUSES,
    )


@app.route("/case/<int:case_id>/print")
@page_guard("csc", "detective", "commander")
def case_print_page(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return redirect(url_for("index"))

    if user.role == "detective" and case.detective_id != user.id:
        return redirect(url_for("index"))
    if user.role == "csc" and case.created_by_id != user.id:
        return redirect(url_for("index"))

    log_action("CASE_PRINTED", target_type="Case", target_id=case.id,
               detail=case.cas_number, actor=user)

    return render_template(
        "case_print.html",
        case=case.to_dict(include_detail=True),
        user=user.to_dict(),
    )


@app.route("/profile")
@page_guard("csc", "detective", "commander")
def profile_page(user):
    return render_template("profile.html",
                           token=request.args.get("token"),
                           user=user.to_dict())


@app.route("/commander")
@page_guard("commander")
def commander_overview(user):
    return render_template("commander/overview.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           active="overview")


@app.route("/commander/personnel")
@page_guard("commander")
def commander_personnel(user):
    return render_template("commander/personnel.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           active="personnel")


@app.route("/commander/register")
@page_guard("commander")
def commander_register(user):
    return render_template("commander/register.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           active="register")


@app.route("/commander/audit")
@page_guard("commander")
def commander_audit(user):
    return render_template("commander/audit.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           active="audit")


@app.route("/commander/dockets")
@page_guard("commander")
def commander_dockets(user):
    return render_template("commander/dockets.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           active="dockets",
                           crime_types=CRIME_TYPES,
                           statuses=CASE_STATUSES)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@app.route("/api/auth/login", methods=["POST"])
@limiter.limit(config.LOGIN_RATE_LIMIT)
def login():
    data = request.get_json(silent=True) or {}
    persal = (data.get("persal_number") or "").strip().upper()
    password = data.get("password") or ""
    if not persal or not password:
        return jsonify({"msg": "PERSAL and password required"}), 400

    user = User.query.filter_by(persal_number=persal).first()
    if not user or not check_password_hash(user.password_hash, password):
        log_action("LOGIN_FAILED", target_type="User",
                   detail=f"Failed login attempt for {persal}")
        return jsonify({"msg": "Invalid credentials"}), 401
    if not user.active:
        return jsonify({"msg": "Account deactivated"}), 403

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "name": user.full_name},
    )
    log_action("LOGIN_SUCCESS", target_type="User", target_id=user.id, actor=user)
    return jsonify({"access_token": token, "user": user.to_dict()}), 200


@app.route("/api/auth/me", methods=["GET"])
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify({"msg": "User not found"}), 404
    return jsonify(user.to_dict()), 200


@app.route("/api/auth/change-password", methods=["POST"])
@jwt_required()
def change_own_password():
    user = db.session.get(User, int(get_jwt_identity()))
    if not user:
        return jsonify({"msg": "User not found"}), 404

    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new_pwd = data.get("new_password") or ""

    if not check_password_hash(user.password_hash, current):
        log_action("PASSWORD_CHANGE_FAILED", target_type="User",
                   target_id=user.id,
                   detail="Wrong current password", actor=user)
        return jsonify({"msg": "Current password is incorrect."}), 400

    err = _validate_password(new_pwd)
    if err:
        return jsonify({"msg": err}), 400

    if check_password_hash(user.password_hash, new_pwd):
        return jsonify({"msg": "New password must differ from the current one."}), 400

    user.password_hash = generate_password_hash(new_pwd)
    db.session.commit()

    log_action("PASSWORD_CHANGED", target_type="User", target_id=user.id,
               actor=user)
    return jsonify({"msg": "Password updated successfully."}), 200


# ---------------------------------------------------------------------------
# Public tracking
# ---------------------------------------------------------------------------
@app.route("/api/public/track", methods=["POST"])
@limiter.limit("30 per minute")
def public_track():
    data = request.get_json(silent=True) or {}
    cas = (data.get("cas_number") or "").strip().upper()
    identifier = (data.get("identifier") or "").strip()
    if not cas or not identifier:
        return jsonify({"msg": "CAS number and SA ID / phone required"}), 400

    case = Case.query.filter_by(cas_number=cas).first()
    if not case:
        return jsonify({"msg": "No docket found for that CAS number"}), 404

    if identifier not in (case.complainant_id, case.complainant_phone):
        log_action("PUBLIC_TRACK_DENIED", target_type="Case", target_id=case.id,
                   detail=f"Bad identifier for {cas}")
        return jsonify({"msg": "Identity does not match this docket"}), 403

    log_action("PUBLIC_TRACK", target_type="Case", target_id=case.id,
               detail=f"Public milestone view for {cas}")

    return jsonify({
        "cas_number": case.cas_number,
        "crime_type": case.crime_type,
        "status": case.status,
        "location": case.location,
        "created_at": case.created_at.isoformat(),
        "milestones": [m.to_dict() for m in case.milestones],
    }), 200


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
@app.route("/api/cases", methods=["POST"])
@roles_required("csc", "commander")
def create_case(user):
    data = request.get_json(silent=True) or {}
    required = ["complainant_name", "complainant_id", "complainant_phone",
                "complainant_email", "crime_type", "description", "location"]
    missing = [k for k in required if not (data.get(k) or "").strip()]
    if missing:
        return jsonify({"msg": f"Missing fields: {', '.join(missing)}"}), 400

    detective = pick_least_loaded_detective()
    if not detective:
        return jsonify({"msg": "No active detective available for assignment"}), 409

    case = Case(
        cas_number=generate_cas_number(),
        complainant_name=data["complainant_name"].strip(),
        complainant_id=data["complainant_id"].strip(),
        complainant_phone=data["complainant_phone"].strip(),
        complainant_email=data["complainant_email"].strip(),
        crime_type=data["crime_type"].strip(),
        description=data["description"].strip(),
        location=data["location"].strip(),
        status="Open",
        detective_id=detective.id,
        created_by_id=user.id,
    )
    db.session.add(case)
    db.session.commit()

    db.session.add(Milestone(
        case_id=case.id,
        title="Docket registered at CSC",
        detail=f"Assigned to {detective.full_name} ({detective.persal_number}).",
        posted_by_id=user.id,
    ))
    db.session.commit()

    log_action("CASE_CREATED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} assigned to {detective.persal_number}",
               actor=user)

    subject, body = case_registered_email(
        case.cas_number, case.complainant_name,
        case.crime_type, detective.full_name,
    )
    email_result = send_email(case.complainant_email, subject, body)
    if email_result.get("ok"):
        log_action("EMAIL_SENT", target_type="Case", target_id=case.id,
                   detail=f"CAS {case.cas_number} emailed to "
                          f"{case.complainant_email}",
                   actor=user)
    else:
        log_action("EMAIL_FAILED", target_type="Case", target_id=case.id,
                   detail=f"Email to {case.complainant_email} failed: "
                          f"{email_result.get('error')}",
                   actor=user)

    result = case.to_dict(include_detail=True)
    result["email"] = email_result
    return jsonify(result), 201


@app.route("/api/cases", methods=["GET"])
@roles_required("csc", "commander", "detective")
def list_cases(user):
    """List cases with role scoping, smart-search filters and pagination."""
    q = Case.query
    if user.role == "detective":
        q = q.filter(Case.detective_id == user.id)
    elif user.role == "csc":
        q = q.filter(Case.created_by_id == user.id)

    q = apply_case_filters(q, request.args)
    q = q.order_by(Case.created_at.desc())

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError):
        per_page = 20
    per_page = max(1, min(per_page, 100))

    total = q.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages

    items = q.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        "cases": [c.to_dict() for c in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }), 200


@app.route("/api/cases/<int:case_id>", methods=["GET"])
@roles_required("csc", "commander", "detective")
def get_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/status", methods=["PATCH"])
@roles_required("detective", "commander")
def update_case_status(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    data = request.get_json(silent=True) or {}
    new_status = (data.get("status") or "").strip()
    if new_status not in CASE_STATUSES:
        return jsonify({"msg": f"Status must be one of {CASE_STATUSES}"}), 400
    case.status = new_status
    db.session.commit()
    log_action("CASE_STATUS_CHANGED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} -> {new_status}", actor=user)
    return jsonify(case.to_dict(include_detail=True)), 200


# ---------------------------------------------------------------------------
# Milestones & evidence
# ---------------------------------------------------------------------------
@app.route("/api/cases/<int:case_id>/milestones", methods=["POST"])
@roles_required("detective", "commander")
def add_milestone(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"msg": "Milestone title required"}), 400

    m = Milestone(case_id=case.id, title=title,
                  detail=(data.get("detail") or "").strip() or None,
                  posted_by_id=user.id)
    db.session.add(m)
    db.session.commit()

    log_action("MILESTONE_ADDED", target_type="Case", target_id=case.id,
               detail=title, actor=user)

    email_result = {"ok": False, "error": "No email address on file"}
    if case.complainant_email:
        subject, body = milestone_email(
            case.cas_number, case.complainant_name,
            m.title, m.detail or "",
            user.full_name, case.status,
        )
        email_result = send_email(case.complainant_email, subject, body)
        if email_result.get("ok"):
            log_action("MILESTONE_EMAIL_SENT", target_type="Case",
                       target_id=case.id,
                       detail=f"Update emailed to {case.complainant_email}",
                       actor=user)
        else:
            log_action("MILESTONE_EMAIL_FAILED", target_type="Case",
                       target_id=case.id,
                       detail=f"Email to {case.complainant_email} failed: "
                              f"{email_result.get('error')}",
                       actor=user)

    result = m.to_dict()
    result["email"] = email_result
    return jsonify(result), 201


@app.route("/api/cases/<int:case_id>/evidence", methods=["POST"])
@roles_required("detective", "commander")
def upload_evidence(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    if "file" not in request.files:
        return jsonify({"msg": "No file part in request"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"msg": "Empty filename"}), 400
    if not allowed_file(file.filename):
        return jsonify({"msg": "File type not allowed"}), 400

    original = secure_filename(file.filename)
    ext = original.rsplit(".", 1)[1].lower() if "." in original else "bin"
    stored_name = f"{uuid.uuid4().hex}_{case.id}.{ext}"
    dest = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
    file.save(dest)

    digest = sha256_of_file(dest)
    ev = Evidence(case_id=case.id, filename=original, stored_name=stored_name,
                  file_hash=digest, file_size=os.path.getsize(dest),
                  content_type=file.content_type, uploaded_by_id=user.id)
    db.session.add(ev)
    db.session.commit()

    m = Milestone(
        case_id=case.id, title="Evidence uploaded",
        detail=f"{original} (SHA-256: {digest[:16]}...)",
        posted_by_id=user.id,
    )
    db.session.add(m)
    db.session.commit()

    log_action("EVIDENCE_UPLOADED", target_type="Case", target_id=case.id,
               detail=f"{original} sha256={digest}", actor=user)

    if case.complainant_email:
        subject, body = milestone_email(
            case.cas_number, case.complainant_name,
            m.title, m.detail or "",
            user.full_name, case.status,
        )
        email_result = send_email(case.complainant_email, subject, body)
        if email_result.get("ok"):
            log_action("MILESTONE_EMAIL_SENT", target_type="Case",
                       target_id=case.id,
                       detail=f"Evidence notice emailed to "
                              f"{case.complainant_email}",
                       actor=user)
        else:
            log_action("MILESTONE_EMAIL_FAILED", target_type="Case",
                       target_id=case.id,
                       detail=f"Email to {case.complainant_email} failed: "
                              f"{email_result.get('error')}",
                       actor=user)

    return jsonify(ev.to_dict()), 201


@app.route("/api/evidence/<int:evidence_id>/download", methods=["GET"])
@jwt_required()
def download_evidence(evidence_id):
    user = db.session.get(User, int(get_jwt_identity()))
    ev = db.session.get(Evidence, evidence_id)
    if not ev or not user:
        return jsonify({"msg": "Not found"}), 404
    case = ev.case
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    log_action("EVIDENCE_DOWNLOADED", target_type="Case", target_id=case.id,
               detail=ev.filename, actor=user)
    return send_from_directory(app.config["UPLOAD_FOLDER"], ev.stored_name,
                               as_attachment=True, download_name=ev.filename)


# ---------------------------------------------------------------------------
# Commander endpoints
# ---------------------------------------------------------------------------
@app.route("/api/users", methods=["GET"])
@roles_required("commander")
def list_users(user):
    users = User.query.order_by(User.role, User.full_name).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route("/api/users", methods=["POST"])
@roles_required("commander")
def create_user(user):
    data = request.get_json(silent=True) or {}
    required = ["persal_number", "full_name", "password", "role"]
    missing = [k for k in required if not (data.get(k) or "").strip()]
    if missing:
        return jsonify({"msg": f"Missing fields: {', '.join(missing)}"}), 400

    persal = data["persal_number"].strip().upper()
    if User.query.filter_by(persal_number=persal).first():
        return jsonify({"msg": "PERSAL number already registered"}), 409

    role = data["role"].strip().lower()
    if role not in {"csc", "detective"}:
        return jsonify({"msg": "Role must be csc or detective"}), 400

    err = _validate_password(data["password"])
    if err:
        return jsonify({"msg": err}), 400

    new_user = User(
        persal_number=persal,
        full_name=data["full_name"].strip(),
        password_hash=generate_password_hash(data["password"]),
        role=role,
        rank=(data.get("rank") or "").strip() or None,
        station=(data.get("station") or user.station).strip(),
        active=True,
    )
    db.session.add(new_user)
    db.session.commit()
    log_action("USER_CREATED", target_type="User", target_id=new_user.id,
               detail=f"{persal} role={role}", actor=user)
    return jsonify(new_user.to_dict()), 201


@app.route("/api/users/<int:user_id>/active", methods=["PATCH"])
@roles_required("commander")
def toggle_user_active(user, user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    if target.id == user.id:
        return jsonify({"msg": "You cannot deactivate yourself"}), 400

    data = request.get_json(silent=True) or {}
    new_state = bool(data.get("active", not target.active))

    reassignment = None

    if new_state is False and target.role == "detective":
        open_cases = Case.query.filter(
            Case.detective_id == target.id,
            Case.status != "Closed",
        ).all()

        if open_cases:
            candidates = User.query.filter(
                User.role == "detective",
                User.active == True,
                User.id != target.id,
            ).all()

            if not candidates:
                return jsonify({
                    "msg": "Cannot deactivate: this detective has "
                           f"{len(open_cases)} open case(s) and no other "
                           "active detective is available to take them."
                }), 409

            def load(d):
                return Case.query.filter(
                    Case.detective_id == d.id,
                    Case.status != "Closed",
                ).count()

            candidates.sort(key=load)
            new_owner = candidates[0]

            moved = 0
            for c in open_cases:
                c.detective_id = new_owner.id
                db.session.add(Milestone(
                    case_id=c.id,
                    title="Case reassigned",
                    detail=(f"Reassigned from {target.full_name} "
                            f"({target.persal_number}) to "
                            f"{new_owner.full_name} ({new_owner.persal_number}) "
                            "due to personnel change."),
                    posted_by_id=user.id,
                ))
                moved += 1

            reassignment = {
                "moved": moved,
                "from": target.full_name,
                "to": new_owner.full_name,
                "to_persal": new_owner.persal_number,
            }

    target.active = new_state
    db.session.commit()

    log_action("USER_ACTIVE_TOGGLED", target_type="User", target_id=target.id,
               detail=f"active={target.active}"
                      + (f" · reassigned {reassignment['moved']} case(s) to "
                         f"{reassignment['to_persal']}" if reassignment else ""),
               actor=user)

    result = target.to_dict()
    if reassignment:
        result["reassignment"] = reassignment
    return jsonify(result), 200


@app.route("/api/users/<int:user_id>/password", methods=["PATCH"])
@roles_required("commander")
def reset_password(user, user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    data = request.get_json(silent=True) or {}
    new_pwd = (data.get("password") or "").strip()

    err = _validate_password(new_pwd)
    if err:
        return jsonify({"msg": err}), 400

    target.password_hash = generate_password_hash(new_pwd)
    db.session.commit()
    log_action("USER_PASSWORD_RESET", target_type="User", target_id=target.id,
               actor=user)
    return jsonify({"msg": "Password updated"}), 200


@app.route("/api/audit", methods=["GET"])
@roles_required("commander")
def audit_logs(user):
    limit = min(int(request.args.get("limit", 200)), 1000)
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify([l.to_dict() for l in logs]), 200


@app.route("/api/stats", methods=["GET"])
@roles_required("commander", "csc")
def stats(user):
    total = Case.query.count()
    open_cases = Case.query.filter(Case.status != "Closed").count()
    detectives = User.query.filter_by(role="detective", active=True).all()
    workload = [{
        "detective": d.full_name,
        "persal_number": d.persal_number,
        "station": d.station,
        "open_cases": Case.query.filter(
            Case.detective_id == d.id, Case.status != "Closed"
        ).count(),
    } for d in detectives]
    return jsonify({
        "total_cases": total,
        "open_cases": open_cases,
        "closed_cases": total - open_cases,
        "detective_workload": workload,
    }), 200


@app.route("/api/stats/charts", methods=["GET"])
@roles_required("commander", "csc")
def stats_charts(user):
    """Aggregate data for the dashboard charts."""

    # --- Cases per month (last 6 months, including this one) ---
    now = datetime.utcnow()
    months = []
    for i in range(5, -1, -1):
        y = now.year
        m = now.month - i
        while m <= 0:
            m += 12
            y -= 1
        months.append((y, m))

    cases_per_month = []
    for (y, m) in months:
        start = datetime(y, m, 1)
        if m == 12:
            end = datetime(y + 1, 1, 1)
        else:
            end = datetime(y, m + 1, 1)
        count = Case.query.filter(
            Case.created_at >= start,
            Case.created_at < end,
        ).count()
        cases_per_month.append({
            "label": start.strftime("%b %Y"),
            "year": y,
            "month": m,
            "count": count,
        })

    # --- Cases by crime type ---
    crime_counts = {}
    for row in Case.query.all():
        ct = row.crime_type or "Other"
        crime_counts[ct] = crime_counts.get(ct, 0) + 1
    cases_by_crime = [
        {"label": k, "count": v}
        for k, v in sorted(crime_counts.items(), key=lambda x: -x[1])
    ]

    # --- Status breakdown ---
    status_counts = {}
    for row in Case.query.all():
        s = row.status or "Open"
        status_counts[s] = status_counts.get(s, 0) + 1
    cases_by_status = [
        {"label": k, "count": v}
        for k, v in sorted(status_counts.items(), key=lambda x: -x[1])
    ]

    return jsonify({
        "cases_per_month": cases_per_month,
        "cases_by_crime": cases_by_crime,
        "cases_by_status": cases_by_status,
    }), 200


# ---------------------------------------------------------------------------
# Bootstrap: create DB + one built-in Branch Commander
# ---------------------------------------------------------------------------
BUILT_IN_COMMANDER = {
    "persal_number": "CMD001",
    "full_name":     "Branch Commander",
    "password":      "Commander@123",
    "rank":          "Colonel",
    "station":       "Central SAPS",
}


def bootstrap_commander():
    if User.query.filter_by(persal_number=BUILT_IN_COMMANDER["persal_number"]).first():
        return
    db.session.add(User(
        persal_number=BUILT_IN_COMMANDER["persal_number"],
        full_name=BUILT_IN_COMMANDER["full_name"],
        password_hash=generate_password_hash(BUILT_IN_COMMANDER["password"]),
        role="commander",
        rank=BUILT_IN_COMMANDER["rank"],
        station=BUILT_IN_COMMANDER["station"],
        active=True,
    ))
    db.session.commit()
    print("=" * 60)
    print(" Built-in Branch Commander created:")
    print(f"   PERSAL   : {BUILT_IN_COMMANDER['persal_number']}")
    print(f"   Password : {BUILT_IN_COMMANDER['password']}")
    print(" Change this password immediately after first login.")
    print("=" * 60)


with app.app_context():
    db.create_all()
    bootstrap_commander()


if __name__ == "__main__":
    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=(config.DEBUG),
    )