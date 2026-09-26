"""
mailer.py — Email delivery for SAPS eDMS via Gmail SMTP.
All credentials are read from config.py (which reads .env).
"""

from flask_mail import Mail, Message
from config import config

mail = Mail()


def init_mail(app):
    """Attach Flask-Mail to the Flask app using settings from config."""
    app.config.setdefault("MAIL_SERVER", config.MAIL_SERVER)
    app.config.setdefault("MAIL_PORT", config.MAIL_PORT)
    app.config.setdefault("MAIL_USE_TLS", config.MAIL_USE_TLS)
    app.config.setdefault("MAIL_USE_SSL", config.MAIL_USE_SSL)
    app.config.setdefault("MAIL_USERNAME", config.MAIL_USERNAME)
    app.config.setdefault("MAIL_PASSWORD", config.MAIL_PASSWORD)
    app.config.setdefault("MAIL_DEFAULT_SENDER", config.MAIL_DEFAULT_SENDER)
    mail.init_app(app)


def send_email(to_address: str, subject: str, body: str):
    """Send an email. Returns {'ok': True} or {'ok': False, 'error': '...'}"""
    if not to_address:
        return {"ok": False, "error": "No recipient email address"}
    try:
        msg = Message(
            subject=subject,
            recipients=[to_address],
            body=body,
        )
        mail.send(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def case_registered_email(cas_number: str, complainant_name: str,
                          crime_type: str, detective_name: str) -> tuple:
    """Return (subject, body) for the docket-registration email."""
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

Keep this CAS number safe — you will need it to follow up on your case.

Do not reply to this email.

SAPS Electronic Docket Management System
"""
    return subject, body


def milestone_email(cas_number: str, complainant_name: str,
                    milestone_title: str, milestone_detail: str,
                    posted_by: str, case_status: str) -> tuple:
    """Return (subject, body) for a milestone-update email."""
    subject = f"SAPS eDMS — Update on docket {cas_number}"

    detail_block = f"\n  {milestone_detail}\n" if milestone_detail else ""

    body = f"""Dear {complainant_name},

There is a new update on your case {cas_number}.

  Update:  {milestone_title}
{detail_block}
  Posted by:  {posted_by}
  Case status: {case_status}

You can view your full case timeline at any time on the SAPS eDMS
public tracker using your CAS number together with your SA ID number
or the phone number you provided.

Do not reply to this email.

SAPS Electronic Docket Management System
"""
    return subject, body