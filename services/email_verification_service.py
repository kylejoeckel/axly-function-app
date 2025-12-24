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
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER or "")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "AXLY.pro")
EMAIL_REPLY_TO = os.getenv("EMAIL_FROM", EMAIL_FROM)
LOGO_URL = os.getenv("EMAIL_LOGO_URL", "https://axly.pro/logo.png")

# ────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────
def _generate_pin() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"

def _send_email(to: str, subject: str, body: str, html_body: str = None) -> None:
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM]):
        raise RuntimeError("SMTP configuration missing")

    msg = EmailMessage()
    msg["From"] = f'{EMAIL_FROM_NAME} <{EMAIL_FROM}>'
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = EMAIL_REPLY_TO
    msg.set_content(body)

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if SMTP_PORT == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg, from_addr=EMAIL_FROM, to_addrs=[to])
    else:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg, from_addr=EMAIL_FROM, to_addrs=[to])

def _purpose_strings(purpose: str) -> tuple[str, str]:
    p = (purpose or "signup").lower()
    if p == "password_reset":
        return (
            "Your AXLY.pro password reset code",
            "Your password reset code is",
        )
    if p == "change_password":
        return (
            "Confirm your AXLY.pro password change",
            "Your password change confirmation code is",
        )
    return (
        "Your AXLY.pro verification code",
        "Your verification code is",
    )

def _build_html_email(pin: str, message_line: str, ttl_minutes: int) -> str:
    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; background-color: #121212; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #121212;">
        <tr>
            <td align="center" style="padding: 40px 20px;">
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 480px; background-color: #1E1E1E; border-radius: 16px; overflow: hidden;">
                    <tr>
                        <td align="center" style="padding: 40px 40px 30px 40px; background: linear-gradient(135deg, #1E1E1E 0%, #2A2A2A 100%);">
                            <img src="{LOGO_URL}" alt="AXLY.pro" width="120" style="display: block; max-width: 120px; height: auto;">
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 0 40px;">
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td style="height: 1px; background: linear-gradient(90deg, transparent, #E53935, transparent);"></td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 30px 40px 20px 40px;">
                            <p style="margin: 0 0 20px 0; color: #B0B0B0; font-size: 16px; line-height: 1.5;">
                                {message_line}:
                            </p>
                            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                                <tr>
                                    <td align="center" style="padding: 20px; background-color: #2A2A2A; border-radius: 12px; border: 1px solid #E53935;">
                                        <span style="font-size: 36px; font-weight: 700; letter-spacing: 8px; color: #FFFFFF; font-family: 'SF Mono', Monaco, 'Courier New', monospace;">
                                            {pin}
                                        </span>
                                    </td>
                                </tr>
                            </table>
                            <p style="margin: 20px 0 0 0; color: #808080; font-size: 14px; text-align: center;">
                                This code expires in {ttl_minutes} minutes.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 40px 40px 40px;">
                            <p style="margin: 0; color: #606060; font-size: 13px; line-height: 1.5;">
                                If you didn't request this code, you can safely ignore this email.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 20px 40px; background-color: #171717; border-top: 1px solid #2A2A2A;">
                            <p style="margin: 0; color: #505050; font-size: 12px; text-align: center;">
                                &copy; {datetime.utcnow().year} AXLY.pro
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

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

    subject, line = _purpose_strings(purpose)

    plain_body = (
        f"Hi,\n\n"
        f"{line}: {pin}\n"
        f"It expires in {ttl_minutes} minutes.\n\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— AXLY.pro"
    )

    html_body = _build_html_email(pin, line, ttl_minutes)

    try:
        _send_email(to=email_lc, subject=subject, body=plain_body, html_body=html_body)
    except Exception as e:
        print(f"ERROR sending verification email: {e}")

    return pin

