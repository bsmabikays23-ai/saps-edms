"""mailer.py — Email delivery for SAPS eDMS via Gmail SMTP."""

from flask_mail import Mail, Message
from config import config

mail = Mail()


def init_mail(app):
    app.config.setdefault("MAIL_SERVER", config.MAIL_SERVER)
    app.config.setdefault("MAIL_PORT", config.MAIL_PORT)
    app.config.setdefault("MAIL_USE_TLS", config.MAIL_USE_TLS)
    app.config.setdefault("MAIL_USE_SSL", config.MAIL_USE_SSL)
    app.config.setdefault("MAIL_USERNAME", config.MAIL_USERNAME)
    app.config.setdefault("MAIL_PASSWORD", config.MAIL_PASSWORD)
    app.config.setdefault("MAIL_DEFAULT_SENDER", config.MAIL_DEFAULT_SENDER)
    mail.init_app(app)


def send_email(to_address: str, subject: str, body: str):
    if not to_address:
        return {"ok": False, "error": "No recipient email address"}

    sender = (mail.app.config.get("MAIL_DEFAULT_SENDER") or "SAPS eDMS <no-reply@example.com>") if mail.app else "SAPS eDMS <no-reply@example.com>"

    try:
        msg = Message(subject=subject, recipients=[to_address], sender=sender, body=body)
        mail.send(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def case_registered_email(cas_number, complainant_name, crime_type, detective_name):
    subject = f"SAPS eDMS — Docket {cas_number} registered"
    body = f"""Dear {complainant_name},

Your case has been registered with the South African Police Service
Electronic Docket Management System (SAPS eDMS).

  Case Reference (CAS): {cas_number}
  Crime Type:           {crime_type}
  Assigned Detective:   {detective_name}

You can track the progress of your case at any time by visiting the
SAPS eDMS public tracker and entering your CAS number together with
your SA ID number or the phone number you provided to the officer.

Keep this CAS number safe.

Do not reply to this email.

SAPS Electronic Docket Management System
"""
    return subject, body


def milestone_email(cas_number, complainant_name, milestone_title,
                    milestone_detail, posted_by, case_status):
    subject = f"SAPS eDMS — Update on docket {cas_number}"
    detail_block = f"\n  {milestone_detail}\n" if milestone_detail else ""
    body = f"""Dear {complainant_name},

There is a new update on your case {cas_number}.

  Update:  {milestone_title}
{detail_block}
  Posted by:  {posted_by}
  Case status: {case_status}

You can view your full case timeline at any time on the SAPS eDMS
public tracker.

Do not reply to this email.

SAPS Electronic Docket Management System
"""
    return subject, body


def password_reset_email(full_name: str, code: str) -> tuple:
    """Return (subject, body) for a password reset code."""
    subject = "SAPS eDMS — Password reset code"
    body = f"""Dear {full_name},

A password reset was requested for your SAPS eDMS account.

  Your one-time code: {code}

This code expires in 15 minutes and can only be used once.

Enter it on the SAPS eDMS password reset screen along with your
PERSAL number and your new password.

If you did not request this reset, ignore this email and contact
your system administrator immediately.

Do not reply to this email.

SAPS Electronic Docket Management System
"""
    return subject, body