import azure.functions as func
import json, logging
from datetime import datetime
from utils.cors import cors_response
from services.email_verification_service import create_verification_pin
from services.app_store_service import app_store_service
from auth.utils import hash_password, verify_password
from auth.token import create_access_token
from auth.deps import current_user_from_request
from db import SessionLocal
from models import User, EmailVerification, UserRole

logger = logging.getLogger(__name__)
bp = func.Blueprint()

@bp.function_name(name="RequestPin")
@bp.route(route="request_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_pin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Request a verification PIN for user registration.

    Checks if email is already registered and sends a verification PIN
    if the email is available for new account creation.

    Args:
        req: HTTP request containing JSON with email field

    Returns:
        HTTP response with success message or error

    Raises:
        400: Missing email
        409: Email already exists
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data  = req.get_json()
        email = (data.get("email") or "").strip().lower()
        if not email:
            return cors_response("Missing email", 400)

        with SessionLocal() as db:
            if db.query(User).filter(User.email == email).first():
                return cors_response("User already exists", 409)

        create_verification_pin(email)
        return cors_response("Verification PIN sent", 200)

    except Exception as e:
        logger.exception("Failed to create verification PIN")
        return cors_response(str(e), 500)



@bp.function_name(name="ConfirmSignup")
@bp.route(route="confirm_signup", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm_signup(req: func.HttpRequest) -> func.HttpResponse:
    """
    Confirm user signup with verification PIN.

    Validates the PIN and creates a new user account with the provided
    email and password.

    Args:
        req: HTTP request containing JSON with email, password, and pin

    Returns:
        HTTP response with user data on success or error message

    Raises:
        400: Missing fields, invalid/expired PIN, or user already exists
        500: Server error
    """
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


@bp.function_name(name="Login")
@bp.route(route="login", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Authenticate user with email and password.

    Validates user credentials and returns access token along with user
    information and subscription status.

    Args:
        req: HTTP request containing JSON with email and password

    Returns:
        HTTP response with access token, user data, and subscription info

    Raises:
        400: Missing email or password
        401: Invalid credentials
        500: Server error
    """
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
        subscription_status = app_store_service.get_user_subscription_status(str(user.id))

        return cors_response(
            json.dumps({
                "success": True,
                "access_token": token,
                "token_type": "bearer",
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "role": user.role.value,
                    "tier": user.tier.value,
                    "is_admin": user.is_admin
                },
                "subscription": {
                    "has_active_subscription": subscription_status.get("has_active_subscription", False),
                    "status": subscription_status.get("status", "expired"),
                    "expires_date": subscription_status.get("expires_date", ""),
                    "product_id": subscription_status.get("product_id", ""),
                    "auto_renew_status": subscription_status.get("auto_renew_status", False)
                }
            }),
            200,
            "application/json",
        )

    except Exception as e:
        logger.exception("Login failed")
        return cors_response(str(e), 500)


@bp.function_name(name="Logout")
@bp.route(route="logout", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def logout(req: func.HttpRequest) -> func.HttpResponse:
    """
    Log out the current user.

    Simple logout endpoint that returns success. Token blacklisting
    would require additional storage implementation.

    Args:
        req: HTTP request

    Returns:
        HTTP response with logout confirmation
    """
    if req.method == "OPTIONS":
        return cors_response(204)
    return cors_response("Logged out", 200)

@bp.function_name(name="RequestChangePasswordPin")
@bp.route(route="request_change_password_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_change_password_pin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Request a PIN for password change confirmation.

    Sends a verification PIN to the authenticated user's email address
    to confirm password change request.

    Args:
        req: HTTP request with Authorization header

    Returns:
        HTTP response with confirmation message

    Raises:
        401: Unauthorized - missing or invalid token
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        try:
            create_verification_pin(user.email, purpose="change_password")
        except TypeError:
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
    Confirm password change with PIN verification.

    Validates the PIN and updates the password for the authenticated user.

    Args:
        req: HTTP request with Authorization header and JSON containing pin and new_password

    Returns:
        HTTP response with success confirmation

    Raises:
        400: Missing pin or new_password
        401: Unauthorized
        404: User not found
        500: Server error
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

            db_user = db.query(User).filter(User.id == user.id).first()
            if not db_user:
                return cors_response("User not found", 404)

            db_user.password_hash = hash_password(new_password)
            db.delete(record)
            db.commit()

        return cors_response("Password updated", 200)

    except Exception as e:
        logger.exception("Failed to confirm change-password")
        return cors_response(str(e), 500)
    
@bp.function_name(name="RequestPasswordResetPin")
@bp.route(route="request_password_reset_pin", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def request_password_reset_pin(req: func.HttpRequest) -> func.HttpResponse:
    """
    Request a PIN for password reset.

    Sends a verification PIN for password reset. Always returns success
    to prevent account enumeration attacks.

    Args:
        req: HTTP request containing JSON with email field

    Returns:
        HTTP response with generic success message

    Raises:
        400: Missing email
        500: Server error
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
        return cors_response("If an account exists for that email, a PIN has been sent.", 200)

    except Exception as e:
        logger.exception("Failed to request password reset PIN")
        return cors_response(str(e), 500)


@bp.function_name(name="ConfirmPasswordReset")
@bp.route(route="confirm_password_reset", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def confirm_password_reset(req: func.HttpRequest) -> func.HttpResponse:
    """
    Confirm password reset with PIN verification.

    Validates the reset PIN and sets a new password for the user.
    Returns a fresh access token for immediate login.

    Args:
        req: HTTP request containing JSON with email, pin, and new_password

    Returns:
        HTTP response with access token and user data

    Raises:
        400: Missing fields or invalid/expired PIN
        404: User not found
        500: Server error
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

@bp.function_name(name="AdminLogin")
@bp.route(route="admin/login", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def admin_login(req: func.HttpRequest) -> func.HttpResponse:
    """
    Authenticate admin users.

    Validates admin user credentials and returns access token.
    Only users with admin role can authenticate through this endpoint.

    Args:
        req: HTTP request containing JSON with email and password

    Returns:
        HTTP response with access token and admin user data

    Raises:
        400: Missing email or password
        401: Invalid credentials
        403: User is not admin
        500: Server error
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
    Create a new admin user.

    Creates a new admin user account. If no admins exist, anyone can create
    the first admin. Otherwise, requires existing admin authentication.

    Args:
        req: HTTP request containing JSON with email and password

    Returns:
        HTTP response with new admin user data

    Raises:
        400: Missing email or password
        403: Admin access required (when admins exist)
        409: Email already exists
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        requester = current_user_from_request(req)

        with SessionLocal() as db:
            admin_exists = db.query(User).filter(User.role == UserRole.ADMIN).first()

            if admin_exists and (not requester or not requester.is_admin):
                return cors_response("Admin access required", 403)

        data = req.get_json()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if not all([email, password]):
            return cors_response("Missing email or password", 400)

        with SessionLocal() as db:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                return cors_response("Email already exists", 409)

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


@bp.function_name(name="DeleteAccount")
@bp.route(route="delete_account", methods=["DELETE", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def delete_account(req: func.HttpRequest) -> func.HttpResponse:
    """
    Delete the authenticated user's account and all associated data.

    This is a permanent action that:
    - Deletes all user's vehicles
    - Deletes all user's conversations
    - Deletes the user account
    - Cancels any active subscriptions (user must cancel separately with provider)

    Args:
        req: HTTP request with Authorization header

    Returns:
        HTTP response confirming deletion or error

    Raises:
        401: Unauthorized (missing or invalid token)
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        user_id = user.id
        user_email = user.email

        logger.info(f"Deleting account for user: {user_email} (ID: {user_id})")

        # Delete user's data (cascading deletes should handle related records)
        # SQLAlchemy relationships with cascade='all, delete-orphan' will handle:
        # - vehicles, conversations, diagnoses, etc.

        with SessionLocal() as db:
            # Re-query the user in this session context
            user_to_delete = db.query(User).filter(User.id == user_id).first()
            if not user_to_delete:
                return cors_response("User not found", 404)

            # Delete related records first to avoid foreign key constraints
            # Delete user subscriptions
            from models import StripeSubscription
            db.query(StripeSubscription).filter(StripeSubscription.user_id == user_id).delete()

            # The User model should have cascade deletes configured for:
            # - vehicles, conversations, messages, etc.
            # If not, you may need to explicitly delete them here

            db.delete(user_to_delete)
            db.commit()

        logger.info(f"Successfully deleted account: {user_email}")

        return cors_response(
            json.dumps({
                "success": True,
                "message": "Account deleted successfully"
            }),
            200,
            "application/json"
        )

    except Exception as e:
        logger.exception("Failed to delete account")
        return cors_response(str(e), 500)