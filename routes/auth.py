import azure.functions as func
import json, logging
from datetime import datetime
from utils.cors import cors_response
from services.email_verification_service import create_verification_pin
from auth.utils import hash_password, verify_password
from auth.token import create_access_token
from auth.deps import current_user_from_request  # used only by /logout here
from db import SessionLocal
from models import User, EmailVerification

logger = logging.getLogger(__name__)
bp = func.Blueprint()

# ────────────────────────────────────────────────────────────
#  /request_pin
# ────────────────────────────────────────────────────────────
@bp.function_name(name="RequestPin")
@bp.route(route="request_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_pin(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data  = req.get_json()
        email = (data.get("email") or "").strip().lower()
        if not email:
            return cors_response("Missing email", 400)

        # ──── NEW: abort if the e-mail is already registered ────
        with SessionLocal() as db:
            if db.query(User).filter(User.email == email).first():
                # 409 Conflict is conventional for “unique key already exists”
                return cors_response("User already exists", 409)

        create_verification_pin(email)        # <- unchanged helper
        return cors_response("Verification PIN sent", 200)

    except Exception as e:
        logger.exception("Failed to create verification PIN")
        return cors_response(str(e), 500)



# ────────────────────────────────────────────────────────────
#  /confirm_signup
# ────────────────────────────────────────────────────────────
@bp.function_name(name="ConfirmSignup")
@bp.route(route="confirm_signup", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm_signup(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)
    try:
        data     = req.get_json()
        email    = data.get("email").strip().lower()
        password = data.get("password").strip()
        pin      = data.get("pin")

        if not all([email, password, pin]):
            return cors_response("Missing fields", 400)

        with SessionLocal() as db:
            record = db.query(EmailVerification).filter(
                EmailVerification.email == email,
                EmailVerification.pin   == pin,
                EmailVerification.expires_at > datetime.utcnow(),
            ).first()
            if not record:
                return cors_response("Invalid or expired PIN", 400)

            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return cors_response("User already exists", 400)

            user = User(email=email, password_hash=hash_password(password))
            db.add(user)
            db.delete(record)
            db.commit()

            return cors_response(
                json.dumps({"id": str(user.id), "email": user.email}),
                201,
                "application/json",
            )

    except Exception as e:
        logger.exception("Failed to confirm signup")
        return cors_response(str(e), 500)


# ────────────────────────────────────────────────────────────
#  /login
# ────────────────────────────────────────────────────────────
@bp.function_name(name="Login")
@bp.route(route="login", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def login(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data     = req.get_json()
        email    = data.get("email").strip().lower()
        password = data.get("password").strip()
        if not all([email, password]):
            return cors_response("Missing email or password", 400)

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()

        if not user or not verify_password(password, user.password_hash):
            return cors_response("Invalid credentials", 401)

        token = create_access_token({"sub": str(user.id)})
        return cors_response(
            json.dumps({"access_token": token, "token_type": "bearer"}),
            200,
            "application/json",
        )

    except Exception as e:
        logger.exception("Login failed")
        return cors_response(str(e), 500)


# ────────────────────────────────────────────────────────────
#  /logout
# ────────────────────────────────────────────────────────────
@bp.function_name(name="Logout")
@bp.route(route="logout", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def logout(req: func.HttpRequest) -> func.HttpResponse:
    # Token black‑listing would need a store; here we just answer 200.
    if req.method == "OPTIONS":
        return cors_response(204)
    return cors_response("Logged out", 200)
