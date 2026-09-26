"""SQLAlchemy models for SAPS eDMS."""
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    persal_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="detective")
    rank = db.Column(db.String(50), nullable=True)
    station = db.Column(db.String(80), nullable=False, default="Central SAPS")
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
            "role": self.role,
            "rank": self.rank,
            "station": self.station,
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
    status = db.Column(db.String(30), default="Open", nullable=False)

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

    def to_dict(self, include_detail=False):
        data = {
            "id": self.id,
            "cas_number": self.cas_number,
            "complainant_name": self.complainant_name,
            "complainant_email": self.complainant_email,
            "crime_type": self.crime_type,
            "description": self.description,
            "location": self.location,
            "status": self.status,
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
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(40), nullable=True)
    target_id = db.Column(db.Integer, nullable=True)
    detail = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "actor": self.actor_label or "anonymous",
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "detail": self.detail,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat(),
        }