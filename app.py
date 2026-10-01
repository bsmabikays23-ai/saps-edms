"""
app.py — SAPS Electronic Docket Management System (eDMS)
"""

import os
import re
import secrets
import hashlib
import uuid
import json
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
from sqlalchemy import or_, text
from dotenv import load_dotenv

from config import config
from models import (
    db, User, Case, Evidence, Milestone, AuditLog, PasswordReset,
    DETECTIVE_SPECIALISATIONS, CASE_TIERS,
    VERIFICATION_STATUSES, APPROVAL_STATUSES,
)
from mailer import (
    init_mail, send_email, case_registered_email, milestone_email,
    password_reset_email,
)
from classifier import classify

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

DECISION_REASONS = [
    "Purely civil matter — no criminal offence",
    "Facts alleged do not constitute a crime",
    "Vague or frivolous allegation",
    "Incorrect forum — belongs to another body",
    "Outside this station's jurisdiction",
]

CLOSURE_REASONS = [
    "Nolle prosequi — NPA declined to prosecute",
    "Court finalisation — verdict or withdrawal",
    "Closed as undetected — all leads exhausted",
    "Withdrawn by complainant (sworn statement)",
    "Inquest / deceased suspect",
]

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
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _append_escalation(case, action, actor, note, station=None):
    history = []
    if case.escalation_history:
        try:
            history = json.loads(case.escalation_history)
        except (TypeError, ValueError):
            history = []

    history.append({
        "time": datetime.utcnow().isoformat(),
        "action": action,
        "actor": actor.full_name if actor else "System",
        "actor_role": actor.role if actor else None,
        "note": note or "",
        "station": station or case.transfer_station,
    })
    case.escalation_history = json.dumps(history)
    return case


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


def generate_cas_number():
    now = datetime.utcnow()
    count = Case.query.filter(
        Case.cas_number.like(f"CAS %/{now.month:02d}/{now.year}%")
    ).count() + 1
    candidate = f"CAS {count:03d}/{now.month:02d}/{now.year}"
    while Case.query.filter_by(cas_number=candidate).first():
        count += 1
        candidate = f"CAS {count:03d}/{now.month:02d}/{now.year}"
    return candidate


def find_duplicate(complainant_id, crime_type, location, description):
    """Return an existing Case if the new one looks like a duplicate, else None."""
    if not complainant_id:
        return None

    desc_norm = (description or "").strip().lower()
    if desc_norm:
        same_desc = Case.query.filter(
            db.func.lower(Case.description) == desc_norm
        ).first()
        if same_desc:
            return same_desc

    base = Case.query.filter(
        Case.complainant_id == complainant_id,
        Case.crime_type == crime_type,
    )
    same_loc = base.filter(Case.location == location).first()
    if same_loc:
        return same_loc

    since = datetime.utcnow() - timedelta(hours=24)
    recent = base.filter(Case.created_at >= since).first()
    if recent:
        return recent

    return None


def pick_detective_for_unit(unit, exclude_id=None):
    q = User.query.filter(User.role == "detective", User.active == True)
    if exclude_id:
        q = q.filter(User.id != exclude_id)
    candidates = q.all()
    if unit:
        specialised = [d for d in candidates if d.specialisation == unit]
        if specialised:
            candidates = specialised
    if not candidates:
        return None
    def load(d):
        return Case.query.filter(
            Case.detective_id == d.id, Case.status != "Closed"
        ).count()
    candidates.sort(key=load)
    return candidates[0]


def apply_case_filters(query, args):
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
    tier = (args.get("case_tier") or "").strip()
    if tier and tier.lower() not in ("all", ""):
        query = query.filter(Case.case_tier == tier)
    vstatus = (args.get("verification_status") or "").strip()
    if vstatus and vstatus.lower() not in ("all", ""):
        query = query.filter(Case.verification_status == vstatus)
    astatus = (args.get("approval_status") or "").strip()
    if astatus and astatus.lower() not in ("all", ""):
        query = query.filter(Case.approval_status == astatus)
    decision = (args.get("decision") or "").strip()
    if decision and decision.lower() not in ("all", ""):
        query = query.filter(Case.decision == decision)
    unit = (args.get("assigned_unit") or "").strip()
    if unit and unit.lower() not in ("all", ""):
        query = query.filter(Case.assigned_unit == unit)
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


def _validate_password(pwd):
    if not pwd or len(pwd) < 8:
        return "Password must be at least 8 characters."
    if not any(c.isdigit() for c in pwd):
        return "Password must contain at least one digit."
    if not any(c.isalpha() for c in pwd):
        return "Password must contain at least one letter."
    return None


def _generate_reset_code():
    return str(secrets.randbelow(1_000_000)).zfill(6)


ROLE_RULES = {
    "csc": {
        "ranks": [
            "Constable", "Sergeant", "Warrant Officer",
            "Senior Warrant Officer", "Chief Warrant Officer",
            "Lieutenant", "Captain",
        ],
        "min_rank_for_specialisation": {},
        "needs_specialisation": False,
    },
    "detective": {
        "ranks": [
            "Sergeant", "Warrant Officer", "Senior Warrant Officer",
            "Chief Warrant Officer", "Lieutenant", "Captain", "Major",
        ],
        "min_rank_for_specialisation": {
            "General Detective": "Sergeant",
            "FCS (Family Violence, Child Protection)": "Sergeant",
            "Serious & Violent Crime": "Sergeant",
            "Commercial Crime": "Sergeant",
            "Organised Crime": "Sergeant",
            "Forensic Services": "Sergeant",
            "Crime Intelligence": "Sergeant",
            "DPCI / Hawks": "Captain",
        },
        "needs_specialisation": True,
    },
}

_RANK_ORDER = [
    "Constable", "Sergeant", "Warrant Officer",
    "Senior Warrant Officer", "Chief Warrant Officer",
    "Lieutenant", "Captain", "Major",
    "Lieutenant Colonel", "Colonel", "Brigadier",
    "Major General", "Lieutenant General", "General",
]


def _rank_index(rank):
    try:
        return _RANK_ORDER.index(rank)
    except ValueError:
        return -1


def validate_user_combination(role, rank, specialisation):
    if role not in ROLE_RULES:
        return "Role must be csc or detective."
    rules = ROLE_RULES[role]
    if rank not in rules["ranks"]:
        return f"Rank '{rank}' is not allowed for role '{role}'."
    if rules["needs_specialisation"]:
        if not specialisation:
            return f"A specialisation is required for role '{role}'."
        min_rank = rules["min_rank_for_specialisation"].get(specialisation)
        if min_rank is None:
            return f"Specialisation '{specialisation}' is not recognised."
        if _rank_index(rank) < _rank_index(min_rank):
            return (f"Rank '{rank}' is too junior for the "
                    f"'{specialisation}' unit. Minimum rank is {min_rank}.")
    else:
        if specialisation:
            return f"Specialisation is not applicable to role '{role}'."
    return None


# ---------------------------------------------------------------------------
# JWT / rate limit
# ---------------------------------------------------------------------------
@jwt.unauthorized_loader
def _missing(reason):   return jsonify({"msg": "Authorization required"}), 401

@jwt.invalid_token_loader
def _invalid(reason):   return jsonify({"msg": "Invalid token"}), 422

@jwt.expired_token_loader
def _expired(h, p):     return jsonify({"msg": "Token expired"}), 401


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
    resp = jsonify({"msg": "Too many attempts. Please wait and try again.", "retry_after": retry_after})
    resp.headers["Retry-After"] = str(retry_after)
    return resp, 429


# ---------------------------------------------------------------------------
# Accountability and audit helpers
# ---------------------------------------------------------------------------
def _case_timeline(case):
    items = []
    for milestone in case.milestones:
        items.append({
            "type": "milestone",
            "id": milestone.id,
            "title": milestone.title,
            "detail": milestone.detail,
            "actor": milestone.posted_by.full_name if milestone.posted_by else "System",
            "created_at": milestone.created_at.isoformat(),
        })
    for log in AuditLog.query.filter_by(target_type="Case", target_id=case.id).order_by(AuditLog.created_at.desc()).all():
        items.append({
            "type": "audit",
            "id": log.id,
            "title": log.action,
            "detail": log.detail,
            "actor": log.actor_label or (log.actor.full_name if log.actor else "System"),
            "created_at": log.created_at.isoformat(),
        })
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return items


def _build_compliance_snapshot():
    total_cases = Case.query.count()
    open_cases = Case.query.filter(Case.status != "Closed").count()
    closed_cases = Case.query.filter(Case.status == "Closed").count()
    refused_cases = Case.query.filter(Case.decision == "Refused").count()
    transferred_cases = Case.query.filter(Case.decision == "Transferred").count()
    approved_cases = Case.query.filter(Case.approval_status == "Approved").count()

    overdue_window = datetime.utcnow() - timedelta(days=14)
    overdue_cases = Case.query.filter(
        Case.status != "Closed",
        Case.updated_at < overdue_window,
    ).count()

    latest_case = Case.query.order_by(Case.created_at.desc()).first()
    avg_resolution_days = None
    resolved_cases = Case.query.filter(Case.closed_at.isnot(None)).all()
    if resolved_cases:
        durations = []
        for item in resolved_cases:
            if item.created_at and item.closed_at:
                delta = item.closed_at - item.created_at
                durations.append(max(0, delta.total_seconds() / 86400))
        if durations:
            avg_resolution_days = round(sum(durations) / len(durations), 2)

    refusal_by_officer = []
    officer_rows = db.session.query(
        AuditLog.actor_label,
        db.func.count(AuditLog.id),
    ).filter(AuditLog.action == "CASE_REFUSED").group_by(AuditLog.actor_label).order_by(db.func.count(AuditLog.id).desc()).all()
    for actor_label, count in officer_rows:
        refusal_by_officer.append({"actor": actor_label or "Unknown", "count": count})

    return {
        "total_cases": total_cases,
        "open_cases": open_cases,
        "closed_cases": closed_cases,
        "refused_cases": refused_cases,
        "transferred_cases": transferred_cases,
        "approved_cases": approved_cases,
        "overdue_cases": overdue_cases,
        "average_resolution_days": avg_resolution_days,
        "latest_case_number": latest_case.cas_number if latest_case else None,
        "refusal_by_officer": refusal_by_officer,
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.route("/")
def index():    return render_template("index.html")

@app.route("/track")
def track_page(): return render_template("track.html")

@app.route("/login")
def login_page(): return redirect(url_for("index") + "#officerLogin")

@app.route("/csc")
@page_guard("csc")
def csc_page(user):
    return render_template("csc.html", token=request.args.get("token"),
                           user=user.to_dict(),
                           crime_types=CRIME_TYPES, statuses=CASE_STATUSES,
                           tiers=CASE_TIERS,
                           verification_statuses=VERIFICATION_STATUSES,
                           approval_statuses=APPROVAL_STATUSES,
                           decision_reasons=DECISION_REASONS)

@app.route("/detective")
@page_guard("detective", "commander")
def detective_page(user):
    return render_template("detective.html", token=request.args.get("token"),
                           user=user.to_dict(),
                           crime_types=CRIME_TYPES, statuses=CASE_STATUSES,
                           tiers=CASE_TIERS,
                           specialisations=DETECTIVE_SPECIALISATIONS)

@app.route("/detective/case/<int:case_id>")
@page_guard("detective", "commander")
def detective_case_page(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return redirect(url_for("detective_page") + f"?token={request.args.get('token','')}")
    if user.role == "detective" and case.detective_id != user.id:
        return redirect(url_for("detective_page") + f"?token={request.args.get('token','')}")
    return render_template("detective_case.html",
                           token=request.args.get("token"),
                           user=user.to_dict(),
                           case=case.to_dict(include_detail=True),
                           statuses=CASE_STATUSES,
                           closure_reasons=CLOSURE_REASONS)

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
    return render_template("case_print.html",
                           case=case.to_dict(include_detail=True),
                           user=user.to_dict())

@app.route("/profile")
@page_guard("csc", "detective", "commander", "admin")
def profile_page(user):
    return render_template("profile.html",
                           token=request.args.get("token"),
                           user=user.to_dict())

@app.route("/commander")
@page_guard("commander")
def commander_overview(user):
    return render_template("commander/overview.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="overview")

@app.route("/commander/approvals")
@page_guard("commander")
def commander_approvals(user):
    return render_template("commander/approvals.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="approvals",
                           decision_reasons=DECISION_REASONS)

@app.route("/commander/dockets")
@page_guard("commander")
def commander_dockets(user):
    return render_template("commander/dockets.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="dockets",
                           crime_types=CRIME_TYPES, statuses=CASE_STATUSES,
                           tiers=CASE_TIERS,
                           verification_statuses=VERIFICATION_STATUSES,
                           approval_statuses=APPROVAL_STATUSES)

@app.route("/commander/personnel")
@page_guard("admin")
def commander_personnel(user):
    return render_template("commander/personnel.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="personnel")

@app.route("/commander/register")
@page_guard("admin", "commander")
def commander_register(user):
    return render_template("commander/register.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="register",
                           specialisations=DETECTIVE_SPECIALISATIONS)

@app.route("/commander/audit")
@page_guard("admin", "commander")
def commander_audit(user):
    return render_template("commander/audit.html",
                           token=request.args.get("token"),
                           user=user.to_dict(), active="audit")


# ---------------------------------------------------------------------------
# Auth endpoints
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


@app.route("/api/auth/forgot-password", methods=["POST"])
@limiter.limit("5 per minute")
def forgot_password():
    data = request.get_json(silent=True) or {}
    persal = (data.get("persal_number") or "").strip().upper()
    generic = {"msg": "If that account exists, a code has been sent."}
    if not persal:
        return jsonify({"msg": "PERSAL number required"}), 400

    user = User.query.filter_by(persal_number=persal).first()
    if not user or not user.active or not user.email:
        log_action("PASSWORD_RESET_REQUESTED_UNKNOWN", target_type="User",
                   detail=f"Reset requested for unknown/inactive: {persal}")
        return jsonify(generic), 200

    PasswordReset.query.filter_by(user_id=user.id, used=False).update({"used": True})
    code = _generate_reset_code()
    entry = PasswordReset(
        user_id=user.id,
        code_hash=generate_password_hash(code),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used=False,
    )
    db.session.add(entry)
    db.session.commit()

    subject, body = password_reset_email(user.full_name, code)
    result = send_email(user.email, subject, body)
    log_action("PASSWORD_RESET_SENT", target_type="User", target_id=user.id,
               detail=f"Reset code emailed ({'ok' if result.get('ok') else result.get('error')})")
    return jsonify(generic), 200


@app.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("10 per minute")
def reset_password_with_code():
    data = request.get_json(silent=True) or {}
    persal = (data.get("persal_number") or "").strip().upper()
    code = (data.get("code") or "").strip()
    new_pwd = data.get("new_password") or ""
    if not persal or not code or not new_pwd:
        return jsonify({"msg": "PERSAL, code, and new password are required"}), 400
    err = _validate_password(new_pwd)
    if err:
        return jsonify({"msg": err}), 400

    user = User.query.filter_by(persal_number=persal).first()
    if not user or not user.active:
        return jsonify({"msg": "Invalid code or expired."}), 400
    entry = PasswordReset.query.filter_by(
        user_id=user.id, used=False
    ).order_by(PasswordReset.created_at.desc()).first()
    if not entry or entry.expires_at < datetime.utcnow():
        return jsonify({"msg": "Invalid code or expired."}), 400
    if not check_password_hash(entry.code_hash, code):
        return jsonify({"msg": "Invalid code or expired."}), 400

    user.password_hash = generate_password_hash(new_pwd)
    entry.used = True
    db.session.commit()
    log_action("PASSWORD_RESET_COMPLETED", target_type="User", target_id=user.id)
    return jsonify({"msg": "Password updated successfully."}), 200


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
                   target_id=user.id, actor=user)
        return jsonify({"msg": "Current password is incorrect."}), 400
    err = _validate_password(new_pwd)
    if err:
        return jsonify({"msg": err}), 400
    if check_password_hash(user.password_hash, new_pwd):
        return jsonify({"msg": "New password must differ from the current one."}), 400
    user.password_hash = generate_password_hash(new_pwd)
    db.session.commit()
    log_action("PASSWORD_CHANGED", target_type="User", target_id=user.id, actor=user)
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
        "verification_status": case.verification_status,
        "case_tier": case.case_tier,
        "assigned_unit": case.assigned_unit,
        "decision": case.decision,
        "decision_reason": case.decision_reason,
        "transfer_station": case.transfer_station,
        "closure_reason": case.closure_reason,
        "created_at": case.created_at.isoformat(),
        "milestones": [m.to_dict() for m in case.milestones],
    }), 200


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
@app.route("/api/register-options", methods=["GET"])
def register_options():
    role_items = [
        {
            "value": "csc",
            "label": "CSC Desk Officer",
            "guidance": "Registers and verifies new dockets at intake.",
            "ranks": [
                "Constable", "Sergeant", "Warrant Officer",
                "Senior Warrant Officer", "Chief Warrant Officer",
                "Lieutenant", "Captain",
            ],
            "needs_specialisation": False,
        },
        {
            "value": "detective",
            "label": "Detective",
            "guidance": "Investigates assigned dockets in a specialist unit.",
            "ranks": [
                "Sergeant", "Warrant Officer", "Senior Warrant Officer",
                "Chief Warrant Officer", "Lieutenant", "Captain", "Major",
            ],
            "needs_specialisation": True,
        },
    ]
    spec_items = []
    for item in DETECTIVE_SPECIALISATIONS:
        min_rank = "Sergeant"
        if item == "DPCI / Hawks":
            min_rank = "Captain"
        spec_items.append({
            "value": item,
            "label": item,
            "handles": f"Handles {item.lower()} dockets.",
            "min_rank": min_rank,
        })
    return jsonify({"roles": role_items, "specialisations": spec_items}), 200


@app.route("/api/users", methods=["GET"])
@roles_required("admin", "commander")
def list_users(user):
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route("/api/users", methods=["POST"])
@roles_required("admin", "commander")
def create_user(user):
    data = request.get_json(silent=True) or {}
    persal = (data.get("persal_number") or "").strip().upper()
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    role = (data.get("role") or "csc").strip().lower()
    rank = (data.get("rank") or "").strip()
    specialisation = (data.get("specialisation") or "").strip() or None
    station = (data.get("station") or "Central SAPS").strip() or "Central SAPS"

    if not persal or not full_name or not email or not password:
        return jsonify({"msg": "PERSAL, full name, email, and password are required."}), 400
    if role not in ROLE_RULES:
        return jsonify({"msg": "Role must be csc or detective."}), 400
    if User.query.filter_by(persal_number=persal).first():
        return jsonify({"msg": "A user with that PERSAL number already exists."}), 409

    err = _validate_password(password)
    if err:
        return jsonify({"msg": err}), 400
    err = validate_user_combination(role, rank, specialisation)
    if err:
        return jsonify({"msg": err}), 400

    new_user = User(
        persal_number=persal,
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        rank=rank,
        station=station,
        specialisation=specialisation,
        active=True,
    )
    db.session.add(new_user)
    db.session.commit()
    log_action("USER_CREATED", target_type="User", target_id=new_user.id,
               detail=f"Created {new_user.role} account for {new_user.full_name}", actor=user)
    return jsonify(new_user.to_dict()), 201


@app.route("/api/users/<int:user_id>/active", methods=["PATCH"])
@roles_required("admin", "commander")
def toggle_user_active(user, user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    data = request.get_json(silent=True) or {}
    active = data.get("active")
    if active is None or not isinstance(active, bool):
        return jsonify({"msg": "Boolean active flag required."}), 400
    target.active = active
    db.session.commit()
    log_action("USER_STATUS_CHANGED", target_type="User", target_id=target.id,
               detail=f"Active set to {active}", actor=user)
    return jsonify(target.to_dict()), 200


@app.route("/api/users/<int:user_id>/send-reset-code", methods=["POST"])
@roles_required("admin", "commander")
def send_reset_code(user, user_id):
    target = db.session.get(User, user_id)
    if not target:
        return jsonify({"msg": "User not found"}), 404
    if not target.email:
        return jsonify({"msg": "This account has no email address on file."}), 400
    PasswordReset.query.filter_by(user_id=target.id, used=False).update({"used": True})
    code = _generate_reset_code()
    db.session.add(PasswordReset(
        user_id=target.id,
        code_hash=generate_password_hash(code),
        expires_at=datetime.utcnow() + timedelta(minutes=15),
        used=False,
    ))
    db.session.commit()
    subject, body = password_reset_email(target.full_name, code)
    send_email(target.email, subject, body)
    log_action("PASSWORD_RESET_SENT", target_type="User", target_id=target.id,
               detail=f"Reset code issued to {target.email}", actor=user)
    return jsonify({"msg": "Reset code sent."}), 200


@app.route("/api/stats", methods=["GET"])
@roles_required("commander", "admin")
def get_stats(user):
    total_cases = Case.query.count()
    open_cases = Case.query.filter(Case.status != "Closed").count()
    closed_cases = Case.query.filter(Case.status == "Closed").count()

    detectives = User.query.filter(User.role == "detective").order_by(User.full_name).all()
    workload = []
    for detective in detectives:
        open_count = Case.query.filter(Case.detective_id == detective.id, Case.status != "Closed").count()
        workload.append({
            "detective": detective.full_name,
            "persal_number": detective.persal_number,
            "specialisation": detective.specialisation,
            "open_cases": open_count,
        })

    return jsonify({
        "total_cases": total_cases,
        "open_cases": open_cases,
        "closed_cases": closed_cases,
        "detective_workload": workload,
    }), 200


@app.route("/api/stats/charts", methods=["GET"])
@roles_required("commander", "admin")
def get_stats_charts(user):
    def month_label(month_dt):
        return month_dt.strftime("%b")

    now = datetime.utcnow()
    months = []
    for offset in range(5, -1, -1):
        target = now.month - offset
        year = now.year
        while target <= 0:
            target += 12
            year -= 1
        while target > 12:
            target -= 12
            year += 1
        start = datetime(year, target, 1)
        if target == 12:
            end_year = year + 1
            end_month = 1
        else:
            end_year = year
            end_month = target + 1
        end = datetime(end_year, end_month, 1)
        count = Case.query.filter(Case.created_at >= start, Case.created_at < end).count()
        months.append({"label": month_label(start), "count": count})

    crime_rows = []
    crime_data = db.session.query(Case.crime_type, db.func.count(Case.id)).group_by(Case.crime_type).order_by(db.func.count(Case.id).desc()).limit(8).all()
    for crime_type, count in crime_data:
        crime_rows.append({"label": crime_type or "Unknown", "count": count})

    status_rows = []
    status_data = db.session.query(Case.status, db.func.count(Case.id)).group_by(Case.status).order_by(db.func.count(Case.id).desc()).all()
    for status_name, count in status_data:
        status_rows.append({"label": status_name or "Unknown", "count": count})

    tier_rows = []
    tier_data = db.session.query(Case.case_tier, db.func.count(Case.id)).group_by(Case.case_tier).order_by(db.func.count(Case.id).desc()).all()
    for tier_name, count in tier_data:
        tier_rows.append({"label": tier_name or "Unspecified", "count": count})

    return jsonify({
        "cases_per_month": months,
        "cases_by_crime": crime_rows,
        "cases_by_status": status_rows,
        "cases_by_tier": tier_rows,
    }), 200


@app.route("/api/audit", methods=["GET"])
@roles_required("admin", "commander")
def list_audit(user):
    limit = request.args.get("limit", type=int)
    if limit is None or limit < 1:
        limit = 200
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify([l.to_dict() for l in logs]), 200


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------
@app.route("/api/cases", methods=["POST"])
@roles_required("csc")
def create_case(user):
    data = request.get_json(silent=True) or {}
    required = ["complainant_name", "complainant_id", "complainant_phone",
                "complainant_email", "crime_type", "description", "location"]
    missing = [k for k in required if not (data.get(k) or "").strip()]
    if missing:
        return jsonify({"msg": f"Missing fields: {', '.join(missing)}"}), 400

    g_sworn = bool(data.get("ground_sworn_statement"))
    g_officer = bool(data.get("ground_officer_present"))
    g_court = bool(data.get("ground_court_order"))
    if not (g_sworn or g_officer or g_court):
        return jsonify({
            "msg": "Please select why this docket is being opened."
        }), 400

    def _float_or_none(v):
        try: return float(v) if v not in (None, "", "null") else None
        except (TypeError, ValueError): return None
    def _int_or_none(v):
        try: return int(v) if v not in (None, "", "null") else None
        except (TypeError, ValueError): return None

    suspect_count = _int_or_none(data.get("num_suspects"))
    if suspect_count is not None and (suspect_count < 0 or suspect_count > 20):
        return jsonify({"msg": "Number of suspects must be between 0 and 20."}), 400

    weapons = data.get("weapons_involved") or []
    if isinstance(weapons, list):
        weapons_str = ", ".join(str(w).strip() for w in weapons if str(w).strip())
    else:
        weapons_str = str(weapons).strip()

    force = bool(data.get("force_duplicate"))
    if not force:
        dup = find_duplicate(
            complainant_id=data["complainant_id"].strip(),
            crime_type=data["crime_type"].strip(),
            location=data["location"].strip(),
            description=data["description"].strip(),
        )
        if dup:
            return jsonify({
                "duplicate": True,
                "existing_cas": dup.cas_number,
                "existing_date": dup.created_at.isoformat(),
                "msg": f"A similar docket already exists: {dup.cas_number} "
                       f"(logged {dup.created_at.strftime('%Y-%m-%d')})."
            }, 409)

    case = Case(
        cas_number=generate_cas_number(),
        complainant_name=data["complainant_name"].strip(),
        complainant_id=data["complainant_id"].strip(),
        complainant_phone=data["complainant_phone"].strip(),
        complainant_email=data["complainant_email"].strip(),
        crime_type=data["crime_type"].strip(),
        description=data["description"].strip(),
        location=data["location"].strip(),
        incident_station=(data.get("incident_station") or "").strip() or None,
        ground_sworn_statement=g_sworn,
        ground_officer_present=g_officer,
        ground_court_order=g_court,
        sworn_statement_ref=(data.get("sworn_statement_ref") or "").strip() or None,
        financial_value=_float_or_none(data.get("financial_value")),
        num_suspects=suspect_count,
        weapons_involved=weapons_str or None,
        status="Open",
        verification_status="Unverified",
        approval_status="Not Required",
        decision="Pending",
        created_by_id=user.id,
    )
    db.session.add(case)
    db.session.commit()

    db.session.add(Milestone(
        case_id=case.id, title="Docket registered at CSC",
        detail="Awaiting verification and classification.",
        posted_by_id=user.id))
    db.session.commit()

    log_action("CASE_CREATED", target_type="Case", target_id=case.id,
               detail=case.cas_number, actor=user)

    subject, body = case_registered_email(
        case.cas_number, case.complainant_name, case.crime_type, "Pending assignment")
    email_result = send_email(case.complainant_email, subject, body)

    result = case.to_dict(include_detail=True)
    result["email"] = email_result
    return jsonify(result), 201


@app.route("/api/cases", methods=["GET"])
@roles_required("csc", "commander", "detective", "admin")
def list_cases(user):
    q = Case.query
    if user.role == "detective":
        q = q.filter(Case.detective_id == user.id)
    elif user.role == "csc":
        q = q.filter(Case.created_by_id == user.id)
    q = apply_case_filters(q, request.args)
    q = q.order_by(Case.created_at.desc())

    try: page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError): page = 1
    try: per_page = int(request.args.get("per_page", 20))
    except (TypeError, ValueError): per_page = 20
    per_page = max(1, min(per_page, 100))

    total = q.count()
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page > total_pages: page = total_pages

    items = q.offset((page - 1) * per_page).limit(per_page).all()
    return jsonify({
        "cases": [c.to_dict() for c in items],
        "total": total, "page": page,
        "per_page": per_page, "total_pages": total_pages,
    }), 200


@app.route("/api/cases/<int:case_id>", methods=["GET"])
@roles_required("csc", "commander", "detective", "admin")
def get_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/verify", methods=["POST"])
@roles_required("csc", "commander")
def verify_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if case.verification_status == "Verified":
        return jsonify({"msg": "Already verified."}), 400

    result = classify(case)
    case.verification_status = "Verified"
    case.case_tier = result["tier"]
    case.classification_reasons = "\n".join(result["reasons"])
    case.assigned_unit = result["recommended_unit"]
    case.detective_id = None
    case.approval_status = "Awaiting Approval"
    case.decision = "Pending"
    case.approved_by_id = None
    case.approved_at = None
    case.updated_at = datetime.utcnow()

    db.session.commit()

    reasons_str = "\n".join(f"• {r}" for r in result["reasons"])
    db.session.add(Milestone(
        case_id=case.id, title="Awaiting commander approval",
        detail=(f"Tier: {result['tier']} (score {result['score']})\n"
                f"Unit: {result['recommended_unit']}\n\n"
                f"Reasoning:\n{reasons_str}"),
        posted_by_id=user.id))
    db.session.commit()

    log_action("CASE_VERIFIED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} → {result['tier']} → {result['recommended_unit']}",
               actor=user)
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/approve", methods=["POST"])
@roles_required("commander")
def approve_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    data = request.get_json(silent=True) or {}
    new_det_id = data.get("detective_id")
    if new_det_id is None:
        return jsonify({"msg": "A detective_id is required."}), 400
    try:
        det_id = int(new_det_id)
    except (TypeError, ValueError):
        return jsonify({"msg": "Invalid detective_id"}), 400
    det = db.session.get(User, det_id)
    if not det or det.role != "detective" or not det.active:
        return jsonify({"msg": "Invalid detective"}), 400

    case.detective_id = det.id
    case.approval_status = "Approved"
    case.decision = "Approved"
    case.approved_by_id = user.id
    case.approved_at = datetime.utcnow()
    case.status = "Under Investigation"
    case.updated_at = datetime.utcnow()
    db.session.commit()

    db.session.add(Milestone(
        case_id=case.id,
        title="Assignment approved by commander",
        detail=f"Assigned detective: {det.full_name} ({det.persal_number})",
        posted_by_id=user.id,
    ))
    db.session.commit()

    log_action("CASE_APPROVED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} approved to {det.full_name}", actor=user)
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/refuse", methods=["POST"])
@roles_required("csc", "commander")
def refuse_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    note = (data.get("note") or "").strip()
    if reason not in DECISION_REASONS:
        return jsonify({"msg": "A valid refusal reason is required."}), 400

    case.decision = "Refused"
    case.decision_reason = reason
    case.decision_note = note or None
    case.decision_by_id = user.id
    case.decision_at = datetime.utcnow()
    case.status = "Closed"
    case.closure_reason = "Refused at intake"
    case.closed_at = datetime.utcnow()
    case.closed_by_id = user.id
    case.approval_status = "Not Required"
    case.updated_at = datetime.utcnow()

    db.session.commit()
    db.session.add(Milestone(
        case_id=case.id, title="Docket refused",
        detail=f"Reason: {reason}\n{note}",
        posted_by_id=user.id))
    db.session.commit()

    log_action("CASE_REFUSED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: {reason}", actor=user)

    if case.complainant_email:
        subject = f"SAPS eDMS — Docket {case.cas_number} refused"
        body = (f"Dear {case.complainant_name},\n\n"
                f"Your complaint {case.cas_number} was reviewed and could not be "
                f"registered as a criminal docket.\n\n"
                f"Reason: {reason}\n"
                + (f"Note: {note}\n\n" if note else "\n") +
                "You may contact the station for further guidance.\n\n"
                "SAPS Electronic Docket Management System")
        send_email(case.complainant_email, subject, body)

    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/transfer", methods=["POST"])
@roles_required("csc", "commander")
def transfer_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    station = (data.get("station") or "").strip()
    note = (data.get("note") or "").strip()
    if not station:
        return jsonify({"msg": "Destination station required."}), 400

    case.decision = "Transferred"
    case.decision_reason = "Outside this station's jurisdiction"
    case.decision_note = note or None
    case.transfer_station = station
    case.decision_by_id = user.id
    case.decision_at = datetime.utcnow()
    case.status = "Closed"
    case.closure_reason = f"Transferred to {station}"
    case.closed_at = datetime.utcnow()
    case.closed_by_id = user.id
    case.approval_status = "Not Required"
    case.updated_at = datetime.utcnow()

    db.session.commit()
    db.session.add(Milestone(
        case_id=case.id, title="Docket transferred",
        detail=f"Transferred to {station}. {note}",
        posted_by_id=user.id))
    db.session.commit()

    log_action("CASE_TRANSFERRED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} → {station}", actor=user)

    if case.complainant_email:
        subject = f"SAPS eDMS — Docket {case.cas_number} transferred"
        body = (f"Dear {case.complainant_name},\n\n"
                f"Your complaint {case.cas_number} has been transferred to "
                f"{station} for investigation.\n\n"
                "Please direct further enquiries to that station.\n\n"
                "SAPS Electronic Docket Management System")
        send_email(case.complainant_email, subject, body)

    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/escalate", methods=["POST"])
@roles_required("csc", "detective", "commander")
def escalate_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404

    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    note = (data.get("note") or "").strip()
    target_station = (data.get("station") or "").strip() or case.transfer_station
    if not reason:
        return jsonify({"msg": "An escalation reason is required."}), 400

    case = _append_escalation(case, "Escalated", user, note or reason, station=target_station)
    case.status = "Under Investigation"
    case.approval_status = "Reassigned"
    case.updated_at = datetime.utcnow()
    if target_station:
        case.transfer_station = target_station

    db.session.add(Milestone(
        case_id=case.id,
        title="Case escalated",
        detail=f"Escalation reason: {reason}\n{(f'Note: {note}' if note else '')}",
        posted_by_id=user.id,
    ))
    db.session.commit()
    log_action("CASE_ESCALATED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: {reason}", actor=user)
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/status", methods=["PATCH"])
@roles_required("detective", "commander", "csc")
def update_case_status(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    status = (data.get("status") or "").strip()
    if status not in CASE_STATUSES:
        return jsonify({"msg": "Invalid status value."}), 400

    case.status = status
    case.updated_at = datetime.utcnow()
    if status == "Closed":
        case.closed_at = datetime.utcnow()
        case.closed_by_id = user.id

    db.session.add(Milestone(
        case_id=case.id,
        title="Case status updated",
        detail=f"Status changed to {status} by {user.full_name}.",
        posted_by_id=user.id,
    ))
    db.session.commit()
    log_action("CASE_STATUS_UPDATED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number} → {status}", actor=user)
    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/close", methods=["POST"])
@roles_required("detective", "commander", "csc")
def close_case(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    reference = (data.get("reference") or "").strip()
    note = (data.get("note") or "").strip()
    if not reason:
        return jsonify({"msg": "Closure reason is required."}), 400
    if reason not in CLOSURE_REASONS:
        return jsonify({"msg": "Invalid closure reason."}), 400

    case.status = "Closed"
    case.closure_reason = reason
    case.closure_reference = reference or None
    case.closure_note = note or None
    case.closed_by_id = user.id
    case.closed_at = datetime.utcnow()
    case.decision = "Closed"
    case.updated_at = datetime.utcnow()

    db.session.add(Milestone(
        case_id=case.id,
        title="Docket closed",
        detail=f"Closure reason: {reason}\nReference: {reference or 'Not supplied'}\n{(f'Note: {note}' if note else '')}",
        posted_by_id=user.id,
    ))
    db.session.commit()
    log_action("CASE_CLOSED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: {reason}", actor=user)

    if case.complainant_email:
        subject = f"SAPS eDMS — Docket {case.cas_number} closed"
        body = (
            f"Dear {case.complainant_name},\n\n"
            f"Your complaint {case.cas_number} has been closed.\n\n"
            f"Closure reason: {reason}\n"
            + (f"Reference: {reference}\n" if reference else "")
            + (f"Note: {note}\n\n" if note else "\n")
            + "You may contact the station for further information.\n\n"
            + "SAPS Electronic Docket Management System"
        )
        send_email(case.complainant_email, subject, body)

    return jsonify(case.to_dict(include_detail=True)), 200


@app.route("/api/cases/<int:case_id>/milestones", methods=["POST"])
@roles_required("detective", "commander", "csc")
def add_milestone(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    detail = (data.get("detail") or "").strip()
    if not title:
        return jsonify({"msg": "Milestone title is required."}), 400

    milestone = Milestone(case_id=case.id, title=title, detail=detail or None, posted_by_id=user.id)
    db.session.add(milestone)
    db.session.commit()
    log_action("CASE_MILESTONE_ADDED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: {title}", actor=user)

    if case.complainant_email:
        subject, body = milestone_email(case.cas_number, case.complainant_name, title, detail, user.full_name, case.status)
        send_email(case.complainant_email, subject, body)

    return jsonify(milestone.to_dict()), 200


@app.route("/api/cases/<int:case_id>/evidence", methods=["POST"])
@roles_required("detective", "commander", "csc")
def upload_evidence(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    if "file" not in request.files:
        return jsonify({"msg": "No file uploaded."}), 400

    uploaded = request.files["file"]
    if not uploaded or uploaded.filename == "":
        return jsonify({"msg": "No file uploaded."}), 400

    filename = secure_filename(uploaded.filename)
    if not allowed_file(filename):
        return jsonify({"msg": "Unsupported file type."}), 400

    stored_name = f"{uuid.uuid4().hex}_{filename}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
    uploaded.save(path)

    file_hash = sha256_of_file(path)
    file_size = os.path.getsize(path)
    evidence = Evidence(
        case_id=case.id,
        filename=filename,
        stored_name=stored_name,
        file_hash=file_hash,
        file_size=file_size,
        content_type=uploaded.mimetype or "application/octet-stream",
        uploaded_by_id=user.id,
    )
    db.session.add(evidence)
    db.session.commit()

    db.session.add(Milestone(
        case_id=case.id,
        title="Evidence uploaded",
        detail=f"File: {filename} ({file_size} bytes)",
        posted_by_id=user.id,
    ))
    db.session.commit()
    log_action("EVIDENCE_UPLOADED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: {filename}", actor=user)
    return jsonify(evidence.to_dict()), 200


@app.route("/api/cases/<int:case_id>/evidence/<int:evidence_id>", methods=["GET"])
def open_evidence(case_id, evidence_id):
    token = request.args.get("token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()

    if not token:
        return jsonify({"msg": "Authentication required."}), 401

    try:
        decoded = decode_token(token)
        user_id = int(decoded["sub"])
    except Exception:
        return jsonify({"msg": "Invalid token."}), 401

    user = db.session.get(User, user_id)
    if not user or not user.active:
        return jsonify({"msg": "Account inactive or missing"}), 403
    if user.role not in {"detective", "commander", "csc"}:
        return jsonify({"msg": "Insufficient privileges"}), 403

    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403

    evidence = db.session.get(Evidence, evidence_id)
    if not evidence or evidence.case_id != case.id:
        return jsonify({"msg": "Evidence not found"}), 404

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], evidence.stored_name)
    if not os.path.exists(file_path):
        return jsonify({"msg": "File not found on disk"}), 404

    log_action("EVIDENCE_ACCESSED", target_type="Case", target_id=case.id,
               detail=f"{case.cas_number}: accessed {evidence.filename} by {user.full_name}", actor=user)

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        evidence.stored_name,
        as_attachment=False,
        download_name=evidence.filename,
    )


@app.route("/api/cases/<int:case_id>/timeline", methods=["GET"])
@roles_required("csc", "commander", "detective", "admin")
def get_case_timeline(user, case_id):
    case = db.session.get(Case, case_id)
    if not case:
        return jsonify({"msg": "Case not found"}), 404
    if user.role == "detective" and case.detective_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    if user.role == "csc" and case.created_by_id != user.id:
        return jsonify({"msg": "Not your docket"}), 403
    return jsonify({"timeline": _case_timeline(case)}), 200


@app.route("/api/compliance", methods=["GET"])
@roles_required("commander", "admin")
def get_compliance(user):
    return jsonify(_build_compliance_snapshot()), 200


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
BUILT_IN_ADMIN = {
    "persal_number": "ADM001",
    "full_name":     "System Administrator",
    "email":         "bsmabika.ys23@gmail.com",
    "password":      "Admin@12345",
    "rank":          "Colonel",
    "station":       "Central SAPS",
}

BUILT_IN_COMMANDER = {
    "persal_number": "CMD001",
    "full_name":     "Branch Commander",
    "email":         "kwanelechamane25@gmail.com",
    "password":      "Commander@123",
    "rank":          "Colonel",
    "station":       "Central SAPS",
}


def _ensure_user(cfg, role):
    try:
        existing = User.query.filter_by(persal_number=cfg["persal_number"]).first()
    except Exception:
        return
    if existing:
        return
    db.session.add(User(
        persal_number=cfg["persal_number"],
        full_name=cfg["full_name"],
        email=cfg.get("email"),
        password_hash=generate_password_hash(cfg["password"]),
        role=role,
        rank=cfg.get("rank"),
        station=cfg["station"],
        active=True,
    ))
    db.session.commit()
    print(f"  Built-in {role} created — PERSAL {cfg['persal_number']} / {cfg['password']}")


def bootstrap_accounts():
    _ensure_user(BUILT_IN_ADMIN, "admin")
    _ensure_user(BUILT_IN_COMMANDER, "commander")


def ensure_schema_compatibility():
    try:
        inspector = db.inspect(db.engine)
        columns = inspector.get_columns('cases')
        has_escalation = any(c['name'] == 'escalation_history' for c in columns)
        if not has_escalation:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE cases ADD COLUMN escalation_history TEXT'))
            print('  [bootstrap] Added missing cases.escalation_history column')
    except Exception as exc:
        print(f'  [bootstrap] schema check skipped: {exc}')


with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        print(f"  [bootstrap] create_all skipped: {e}")
    ensure_schema_compatibility()
    bootstrap_accounts()


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=(config.DEBUG))