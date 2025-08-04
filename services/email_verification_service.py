import random
from datetime import datetime, timedelta
from models import EmailVerification
from db import SessionLocal
import os, smtplib, ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "joeckel.kyle@gmail.com"
SMTP_PASS = "rdiovvautrbprdnd"
EMAIL_FROM = "joeckel.kyle@gmail.com"

def _generate_pin() -> str:
    return f"{random.randint(100000, 999999)}"

def _send_email(to: str, subject: str, body: str) -> None:
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS]):
        raise RuntimeError("SMTP environment variables not fully configured")

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"]   = to
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        if SMTP_PORT == 587:
            server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def create_verification_pin(email: str) -> str:
    db = SessionLocal()
    pin = _generate_pin()
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    db.query(EmailVerification).filter(EmailVerification.email == email).delete()
    db.add(EmailVerification(email=email.lower(), pin=pin, expires_at=expires_at))
    db.commit()
    db.close()

    try:
        _send_email(
            to=email,
            subject="Your DiagCar verification code",
            body=(
                f"Hi there,\n\n"
                f"Your DiagCar sign-up code is: {pin}\n"
                f"It expires in 10 minutes.\n\n"
                f"Happy wrenching!\n"
                f"— DiagCar Team"
            ),
        )
    except Exception as e:
        print(f"ERROR sending e-mail: {e}")

    return pin
