import azure.functions as func
import json, logging
from datetime import datetime
from utils.cors import cors_response
from services.email_verification_service import create_verification_pin
from auth.utils import hash_password, verify_password
from auth.token import create_access_token
from auth.deps import current_user_from_request
from db import SessionLocal
from models import User, EmailVerification, UserRole

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

            user = User(email=email, password_hash=hash_password(password), role=UserRole.USER)
            db.add(user)
            db.delete(record)
            db.commit()

            return cors_response(
                json.dumps({
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "is_admin": user.is_admin
                }),
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
            json.dumps({
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "tier": user.tier.value,
                    "is_admin": user.is_admin
                }
            }),
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

# ────────────────────────────────────────────────────────────
#  CHANGE PASSWORD (logged-in flow)
# ────────────────────────────────────────────────────────────

@bp.function_name(name="RequestChangePasswordPin")
@bp.route(route="request_change_password_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_change_password_pin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sends a PIN to the current user's email to confirm a password change.
    Requires Authorization header; doesn't reveal any other info.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        # Send a PIN labeled for the 'change_password' purpose
        try:
            create_verification_pin(user.email, purpose="change_password")
        except TypeError:
            # Backward compat if your helper doesn't accept 'purpose' yet
            create_verification_pin(user.email)

        return cors_response("Verification PIN sent", 200)
    except Exception as e:
        logger.exception("Failed to request change-password PIN")
        return cors_response(str(e), 500)


@bp.function_name(name="ConfirmChangePassword")
@bp.route(route="confirm_change_password", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm_change_password(req: func.HttpRequest) -> func.HttpResponse:
    """
    Confirms the PIN and updates the password for the logged-in user.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        data = req.get_json()
        pin = (data.get("pin") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        if not pin or not new_password:
            return cors_response("Missing pin or new_password", 400)

        with SessionLocal() as db:
            # Look up a valid, unexpired PIN for this user (optionally by purpose)
            qry = db.query(EmailVerification).filter(
                EmailVerification.email == user.email,
                EmailVerification.pin == pin,
                EmailVerification.expires_at > datetime.utcnow(),
            )
            if hasattr(EmailVerification, "purpose"):
                qry = qry.filter(EmailVerification.purpose == "change_password")

            record = qry.first()
            if not record:
                return cors_response("Invalid or expired PIN", 400)

            # Update password
            db_user = db.query(User).filter(User.id == user.id).first()
            if not db_user:
                return cors_response("User not found", 404)

            db_user.password_hash = hash_password(new_password)
            db.delete(record)  # one-time use
            db.commit()

        return cors_response("Password updated", 200)

    except Exception as e:
        logger.exception("Failed to confirm change-password")
        return cors_response(str(e), 500)
    
# ────────────────────────────────────────────────────────────
#  FORGOT PASSWORD (not logged-in flow)
# ────────────────────────────────────────────────────────────

@bp.function_name(name="RequestPasswordResetPin")
@bp.route(route="request_password_reset_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_password_reset_pin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Sends a PIN for password reset. To avoid account enumeration,
    we always return 200 even if the email is unknown.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        email = (data.get("email") or "").strip().lower()
        if not email:
            return cors_response("Missing email", 400)

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()

        if user:
            try:
                create_verification_pin(email, purpose="password_reset")
            except TypeError:
                create_verification_pin(email)

        # Always 200 to prevent email enumeration
        return cors_response("If an account exists for that email, a PIN has been sent.", 200)

    except Exception as e:
        logger.exception("Failed to request password reset PIN")
        return cors_response(str(e), 500)


@bp.function_name(name="ConfirmPasswordReset")
@bp.route(route="confirm_password_reset", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm_password_reset(req: func.HttpRequest) -> func.HttpResponse:
    """
    Confirms the reset PIN and sets a new password for the given email.
    Returns a fresh access token so the user is signed in afterward.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        email = (data.get("email") or "").strip().lower()
        pin = (data.get("pin") or "").strip()
        new_password = (data.get("new_password") or "").strip()

        if not all([email, pin, new_password]):
            return cors_response("Missing fields", 400)

        with SessionLocal() as db:
            # Validate PIN
            qry = db.query(EmailVerification).filter(
                EmailVerification.email == email,
                EmailVerification.pin == pin,
                EmailVerification.expires_at > datetime.utcnow(),
            )
            if hasattr(EmailVerification, "purpose"):
                qry = qry.filter(EmailVerification.purpose == "password_reset")

            record = qry.first()
            if not record:
                return cors_response("Invalid or expired PIN", 400)

            user = db.query(User).filter(User.email == email).first()
            if not user:
                # Very unlikely if we sent a PIN only for existing users,
                # but still protect logic.
                return cors_response("User not found", 404)

            user.password_hash = hash_password(new_password)
            db.delete(record)
            db.commit()

            token = create_access_token({"sub": str(user.id)})

        return cors_response(
            json.dumps({
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "tier": user.tier.value,
                    "is_admin": user.is_admin
                }
            }),
            200,
            "application/json",
        )

    except Exception as e:
        logger.exception("Failed to confirm password reset")
        return cors_response(str(e), 500)

# ────────────────────────────────────────────────────────────
#  ADMIN ENDPOINTS
# ────────────────────────────────────────────────────────────

@bp.function_name(name="AdminLogin")
@bp.route(route="admin/login", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def admin_login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Admin login endpoint - only allows admin users to authenticate
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        email = data.get("email").strip().lower()
        password = data.get("password").strip()
        if not all([email, password]):
            return cors_response("Missing email or password", 400)

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()

        if not user or not verify_password(password, user.password_hash):
            return cors_response("Invalid credentials", 401)

        # Check if user is admin
        if not user.is_admin:
            return cors_response("Access denied", 403)

        token = create_access_token({"sub": str(user.id)})
        return cors_response(
            json.dumps({
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "is_admin": True
                }
            }),
            200,
            "application/json",
        )

    except Exception as e:
        logger.exception("Admin login failed")
        return cors_response(str(e), 500)

@bp.function_name(name="CreateAdmin")
@bp.route(route="admin/create", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def create_admin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Create admin user endpoint - for initial setup or by existing admins
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        # Check if requester is admin (if any admins exist)
        requester = current_user_from_request(req)

        with SessionLocal() as db:
            admin_exists = db.query(User).filter(User.role == UserRole.ADMIN).first()

            # If admins exist, require admin auth
            if admin_exists and (not requester or not requester.is_admin):
                return cors_response("Admin access required", 403)

        data = req.get_json()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if not all([email, password]):
            return cors_response("Missing email or password", 400)

        with SessionLocal() as db:
            # Check if email already exists
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return cors_response("Email already exists", 409)

            # Create admin user
            admin_user = User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN
            )
            db.add(admin_user)
            db.commit()

            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Admin user created successfully",
                    "user": {
                        "id": str(admin_user.id),
                        "email": admin_user.email,
                        "role": admin_user.role.value
                    }
                }),
                201,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to create admin user")
        return cors_response(str(e), 500)