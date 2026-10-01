"""SQLAlchemy models for SAPS eDMS."""
import json
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


DETECTIVE_SPECIALISATIONS = [
    "General Detective",
    "FCS (Family Violence, Child Protection)",
    "Serious & Violent Crime",
    "Commercial Crime",
    "Organised Crime",
    "Forensic Services",
    "Crime Intelligence",
    "DPCI / Hawks",
]

CASE_TIERS = [
    "Light / Routine",
    "Small / Standard",
    "Serious / Complex",
    "Priority / Highly Complex",
]

VERIFICATION_STATUSES = ["Unverified", "Verified"]
APPROVAL_STATUSES = ["Not Required", "Awaiting Approval", "Approved", "Reassigned"]


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    persal_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="detective")
    rank = db.Column(db.String(50), nullable=True)
    station = db.Column(db.String(80), nullable=False, default="Central SAPS")
    specialisation = db.Column(db.String(80), nullable=True)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assigned_cases = db.relationship(
        "Case", backref="assigned_detective", lazy=True,
        foreign_keys="Case.detective_id"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "persal_number": self.persal_number,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "rank": self.rank,
            "station": self.station,
            "specialisation": self.specialisation,
            "active": self.active,
            "open_cases": len([c for c in self.assigned_cases if c.status != "Closed"]),
        }


class Case(db.Model):
    __tablename__ = "cases"
    id = db.Column(db.Integer, primary_key=True)
    cas_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    complainant_name = db.Column(db.String(120), nullable=False)
    complainant_id = db.Column(db.String(20), nullable=False, index=True)
    complainant_phone = db.Column(db.String(20), nullable=False, index=True)
    complainant_email = db.Column(db.String(120), nullable=True)
    crime_type = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    location = db.Column(db.String(150), nullable=False)
    incident_station = db.Column(db.String(80), nullable=True)

    ground_sworn_statement = db.Column(db.Boolean, default=False, nullable=False)
    ground_officer_present = db.Column(db.Boolean, default=False, nullable=False)
    ground_court_order = db.Column(db.Boolean, default=False, nullable=False)
    sworn_statement_ref = db.Column(db.String(80), nullable=True)

    financial_value = db.Column(db.Float, nullable=True)
    num_suspects = db.Column(db.Integer, nullable=True)
    weapons_involved = db.Column(db.String(255), nullable=True)

    case_tier = db.Column(db.String(40), nullable=True)
    classification_reasons = db.Column(db.Text, nullable=True)
    assigned_unit = db.Column(db.String(80), nullable=True)
    escalation_history = db.Column(db.Text, nullable=True)

    decision = db.Column(db.String(20), default="Pending", nullable=False)
    decision_reason = db.Column(db.String(80), nullable=True)
    decision_note = db.Column(db.Text, nullable=True)
    decision_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decision_at = db.Column(db.DateTime, nullable=True)
    transfer_station = db.Column(db.String(80), nullable=True)

    closure_reason = db.Column(db.String(80), nullable=True)
    closure_reference = db.Column(db.String(80), nullable=True)
    closure_note = db.Column(db.Text, nullable=True)
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(30), default="Open", nullable=False)
    verification_status = db.Column(db.String(20), default="Unverified", nullable=False)
    approval_status = db.Column(db.String(30), default="Not Required", nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)

    detective_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    evidence_items = db.relationship(
        "Evidence", backref="case", lazy=True, cascade="all, delete-orphan"
    )
    milestones = db.relationship(
        "Milestone", backref="case", lazy=True, cascade="all, delete-orphan",
        order_by="Milestone.created_at"
    )
    approver = db.relationship("User", foreign_keys=[approved_by_id])
    decision_user = db.relationship("User", foreign_keys=[decision_by_id])
    closer = db.relationship("User", foreign_keys=[closed_by_id])

    def to_dict(self, include_detail=False):
        reasons = []
        if self.classification_reasons:
            reasons = [r for r in self.classification_reasons.split("\n") if r.strip()]
        weapons = []
        if self.weapons_involved:
            weapons = [w.strip() for w in self.weapons_involved.split(",") if w.strip()]
        escalation_history = []
        if self.escalation_history:
            try:
                escalation_history = json.loads(self.escalation_history)
            except (TypeError, ValueError):
                escalation_history = []

        data = {
            "id": self.id,
            "cas_number": self.cas_number,
            "complainant_name": self.complainant_name,
            "complainant_email": self.complainant_email,
            "complainant_phone": self.complainant_phone,
            "complainant_id": self.complainant_id,
            "crime_type": self.crime_type,
            "description": self.description,
            "location": self.location,
            "incident_station": self.incident_station,
            "ground_sworn_statement": self.ground_sworn_statement,
            "ground_officer_present": self.ground_officer_present,
            "ground_court_order": self.ground_court_order,
            "sworn_statement_ref": self.sworn_statement_ref,
            "financial_value": self.financial_value,
            "num_suspects": self.num_suspects,
            "weapons_involved": weapons,
            "case_tier": self.case_tier,
            "classification_reasons": reasons,
            "assigned_unit": self.assigned_unit,
            "escalation_history": escalation_history,
            "decision": self.decision,
            "decision_reason": self.decision_reason,
            "decision_note": self.decision_note,
            "decision_by": self.decision_user.full_name if self.decision_user else None,
            "decision_at": self.decision_at.isoformat() if self.decision_at else None,
            "transfer_station": self.transfer_station,
            "closure_reason": self.closure_reason,
            "closure_reference": self.closure_reference,
            "closure_note": self.closure_note,
            "closed_by": self.closer.full_name if self.closer else None,
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "status": self.status,
            "verification_status": self.verification_status,
            "approval_status": self.approval_status,
            "approved_by": self.approver.full_name if self.approver else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "detective": (
                self.assigned_detective.to_dict()
                if self.assigned_detective else None
            ),
            "latest_milestone": (
                self.milestones[-1].to_dict() if self.milestones else None
            ),
            "milestone_count": len(self.milestones),
            "evidence_count": len(self.evidence_items),
        }
        if include_detail:
            data["milestones"] = [m.to_dict() for m in self.milestones]
            data["evidence"] = [e.to_dict() for e in self.evidence_items]
        return data


class Milestone(db.Model):
    __tablename__ = "milestones"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("cases.id"), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    detail = db.Column(db.Text, nullable=True)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    posted_by = db.relationship("User", foreign_keys=[posted_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "title": self.title,
            "detail": self.detail,
            "posted_by": self.posted_by.full_name if self.posted_by else "System",
            "created_at": self.created_at.isoformat(),
        }


class Evidence(db.Model):
    __tablename__ = "evidence"
    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("cases.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    file_hash = db.Column(db.String(64), nullable=False)
    file_size = db.Column(db.Integer, nullable=False, default=0)
    content_type = db.Column(db.String(100), nullable=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "case_id": self.case_id,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "uploaded_by": self.uploaded_by.full_name if self.uploaded_by else "Unknown",
            "uploaded_at": self.uploaded_at.isoformat(),
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    actor_label = db.Column(db.String(120), nullable=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    target_type = db.Column(db.String(80), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    actor = db.relationship("User", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "actor": self.actor_label or (self.actor.full_name if self.actor else "System"),
            "detail": self.detail,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat(),
        }


class PasswordReset(db.Model):
    __tablename__ = "password_resets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])