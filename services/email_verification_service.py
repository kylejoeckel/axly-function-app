import os
import ssl
import smtplib
import secrets
from email.message import EmailMessage
from datetime import datetime, timedelta

from db import SessionLocal
from models import EmailVerification


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")             # e.g. no-reply@axly.pro (best) or your Gmail (interim)
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "AXLY.pro")
EMAIL_REPLY_TO = os.getenv("EMAIL_FROM", EMAIL_FROM)

# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

def _send_email(to: str, subject: str, body: str) -> None:
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM]):
        raise RuntimeError("SMTP configuration missing")

    msg = EmailMessage()
    msg["From"] = f'{EMAIL_FROM_NAME} <{EMAIL_FROM}>'
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = EMAIL_REPLY_TO
    msg.set_content(body)
    
    if SMTP_PORT == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg, from_addr=EMAIL_FROM, to_addrs=[to])  # envelope-from
    else:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg, from_addr=EMAIL_FROM, to_addrs=[to])  # envelope-from

def _purpose_strings(purpose: str) -> tuple[str, str]:
    """
    Returns (subject, line) where 'line' is used in the email body.
    """
    p = (purpose or "signup").lower()
    if p == "password_reset":
        return (
            "Your AXLY.pro password reset code",
            "Your AXLY.pro password reset code is",
        )
    if p == "change_password":
        return (
            "Confirm your AXLY.pro password change",
            "Use this AXLY.pro code to confirm your password change",
        )
    return (
        "Your AXLY.pro verification code",
        "Your AXLY.pro verification code is",
    )

def create_verification_pin(email: str, purpose: str = "signup", ttl_minutes: int = 10) -> str:
    """
    Create (or replace) a verification PIN for (email, purpose), store it with expiry,
    and email it to the user. Returns the PIN (useful for tests; do not log in prod).
    """
    email_lc = (email or "").strip().lower()
    if not email_lc:
        raise ValueError("email is required")

    pin = _generate_pin()
    expires_at = datetime.utcnow() + timedelta(minutes=ttl_minutes)

    with SessionLocal() as db:
        # One active code per (email, purpose)
        q = db.query(EmailVerification).filter(EmailVerification.email == email_lc)
        if hasattr(EmailVerification, "purpose"):
            q = q.filter(EmailVerification.purpose == purpose)
        q.delete(synchronize_session=False)

        # Create new record
        kwargs = {
            "email": email_lc,
            "pin": pin,
            "expires_at": expires_at,
        }
        if hasattr(EmailVerification, "purpose"):
            kwargs["purpose"] = purpose

        db.add(EmailVerification(**kwargs))
        db.commit()

    # Build AXLY.pro email
    subject, line = _purpose_strings(purpose)
    body = (
        f"Hi,\n\n"
        f"{line}: {pin}\n"
        f"It expires in {ttl_minutes} minutes.\n\n"
        f"If you didn’t request this, you can safely ignore this email.\n\n"
        f"— AXLY.pro"
    )

    try:
        _send_email(to=email_lc, subject=subject, body=body)
    except Exception as e:
        # Don't raise here to avoid leaking SMTP issues to the client; log instead.
        # In production, prefer logger.exception(...)
        print(f"ERROR sending verification email: {e}")

    return pin

