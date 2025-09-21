import azure.functions as func
import json
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from auth.token import create_access_token
from services.app_store_service import app_store_service
from db import SessionLocal
from models import User, UserSubscription, SubscriptionPlatform

logger = logging.getLogger(__name__)
bp = func.Blueprint()

@bp.function_name(name="ValidateReceipt")
@bp.route(route="subscriptions/validate_receipt", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def validate_receipt(req: func.HttpRequest) -> func.HttpResponse:
    """
    Validate an App Store receipt and update user subscription status

    Expected payload:
    {
        "receipt_data": "base64_encoded_receipt_data",
        "platform": "apple_app_store"
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        data = req.get_json()
        receipt_data = data.get("receipt_data")
        platform = data.get("platform", "apple_app_store")

        if not receipt_data:
            return cors_response("Missing receipt_data", 400)

        if platform != "apple_app_store":
            return cors_response("Only Apple App Store supported currently", 400)

        success, response_data = app_store_service.validate_receipt(receipt_data, str(user.id))

        if success:
            subscription_status = app_store_service.get_user_subscription_status(str(user.id))
            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Receipt validated successfully",
                    "subscription": subscription_status
                }),
                200,
                "application/json"
            )
        else:
            error_message = response_data.get("error", "Receipt validation failed")
            apple_status = response_data.get("status", "unknown")

            return cors_response(
                json.dumps({
                    "success": False,
                    "message": error_message,
                    "apple_status": apple_status
                }),
                400,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to validate receipt")
        return cors_response(
            json.dumps({
                "success": False,
                "message": "Internal server error"
            }),
            500,
            "application/json"
        )

@bp.function_name(name="SubscriptionStatus")
@bp.route(route="subscriptions/status", methods=["GET", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def subscription_status(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get current subscription status for the authenticated user
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        status = app_store_service.get_user_subscription_status(str(user.id))
        return cors_response(
            json.dumps(status),
            200,
            "application/json"
        )

    except Exception as e:
        logger.exception("Failed to get subscription status")
        return cors_response("Internal server error", 500)

@bp.function_name(name="RefreshSubscription")
@bp.route(route="subscriptions/refresh", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def refresh_subscription(req: func.HttpRequest) -> func.HttpResponse:
    """
    Refresh subscription status by re-validating the latest receipt

    Expected payload:
    {
        "receipt_data": "base64_encoded_receipt_data"
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        data = req.get_json()
        receipt_data = data.get("receipt_data")

        if not receipt_data:
            return cors_response("Missing receipt_data", 400)

        success, response_data = app_store_service.refresh_subscription_status(str(user.id), receipt_data)

        if success:
            subscription_status = app_store_service.get_user_subscription_status(str(user.id))
            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Subscription status refreshed",
                    "subscription": subscription_status
                }),
                200,
                "application/json"
            )
        else:
            return cors_response(
                json.dumps({
                    "success": False,
                    "message": "Failed to refresh subscription status"
                }),
                400,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to refresh subscription")
        return cors_response(
            json.dumps({
                "success": False,
                "message": "Internal server error"
            }),
            500,
            "application/json"
        )

@bp.function_name(name="AppStoreWebhook")
@bp.route(route="webhooks/app_store", methods=["POST"],
          auth_level=func.AuthLevel.ANONYMOUS)
def app_store_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Handle App Store Server Notifications
    This endpoint will be called by Apple when subscription status changes
    """
    try:
        # Get raw body for signature verification
        raw_body = req.get_body()

        # TODO: Verify the notification signature using Apple's certificate
        # This is critical for security in production

        notification_data = json.loads(raw_body.decode('utf-8'))

        # Store notification for processing
        from models import AppStoreNotification
        from db import SessionLocal

        with SessionLocal() as db:
            notification = AppStoreNotification(
                notification_type=notification_data.get("notification_type", "unknown"),
                transaction_id=notification_data.get("transaction_id"),
                original_transaction_id=notification_data.get("original_transaction_id"),
                product_id=notification_data.get("auto_renew_product_id") or notification_data.get("product_id", "unknown"),
                raw_payload=raw_body.decode('utf-8'),
                processed=False
            )
            db.add(notification)
            db.commit()

            logger.info(f"Stored App Store notification: {notification.notification_type}")

        # TODO: Process the notification asynchronously
        # For now, just acknowledge receipt
        return func.HttpResponse("OK", status_code=200)

    except Exception as e:
        logger.exception("Failed to process App Store webhook")
        return func.HttpResponse("Error", status_code=500)

@bp.function_name(name="AuthWithReceipt")
@bp.route(route="auth/receipt", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def auth_with_receipt(req: func.HttpRequest) -> func.HttpResponse:
    """
    Authenticate user using App Store receipt (subscription-first auth)
    Creates account automatically if needed, returns JWT token

    Expected payload:
    {
        "receipt_data": "base64_encoded_receipt_data",
        "device_id": "optional_device_identifier"
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        receipt_data = data.get("receipt_data")
        device_id = data.get("device_id")

        if not receipt_data:
            return cors_response("Missing receipt_data", 400)

        # First validate the receipt with Apple
        success, apple_response = app_store_service._make_validation_request(
            app_store_service.PRODUCTION_URL,
            {
                "receipt-data": receipt_data,
                "password": app_store_service.app_store_password,
                "exclude-old-transactions": True
            }
        )

        # Try sandbox if production fails with 21007
        if apple_response.get("status") == 21007:
            success, apple_response = app_store_service._make_validation_request(
                app_store_service.SANDBOX_URL,
                {
                    "receipt-data": receipt_data,
                    "password": app_store_service.app_store_password,
                    "exclude-old-transactions": True
                }
            )

        if not success or apple_response.get("status") != 0:
            return cors_response(
                json.dumps({
                    "success": False,
                    "message": "Invalid receipt",
                    "apple_status": apple_response.get("status", "unknown")
                }),
                401,
                "application/json"
            )

        # Extract transaction info to find or create user
        receipt = apple_response.get("receipt", {})
        latest_receipt_info = apple_response.get("latest_receipt_info", [])
        transactions = latest_receipt_info if latest_receipt_info else receipt.get("in_app", [])

        if not transactions:
            return cors_response("No valid transactions in receipt", 400)

        # Use the first (or most recent) transaction to identify user
        transaction = transactions[0] if transactions else None
        original_transaction_id = (
            transaction.get("original_transaction_id") or
            transaction.get("transaction_id")
        )

        if not original_transaction_id:
            return cors_response("Invalid transaction data", 400)

        with SessionLocal() as db:
            # Look for existing subscription with this transaction ID
            existing_subscription = db.query(UserSubscription).filter(
                UserSubscription.transaction_id == original_transaction_id,
                UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
            ).first()

            if existing_subscription:
                # User exists, validate their receipt and return token
                user = existing_subscription.user
                app_store_service.validate_receipt(receipt_data, str(user.id))

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
                            "created_via_receipt": True
                        },
                        "subscription": subscription_status
                    }),
                    200,
                    "application/json"
                )
            else:
                # New user - create account automatically
                # Generate a unique email based on transaction ID
                auto_email = f"appstore_{original_transaction_id}@axly.app"

                # Check if somehow this email already exists
                existing_user = db.query(User).filter(User.email == auto_email).first()
                if existing_user:
                    user = existing_user
                else:
                    # Create new user (no password needed for App Store users)
                    user = User(
                        email=auto_email,
                        password_hash="",  # Empty for App Store-only accounts
                        created_via_receipt=True
                    )
                    db.add(user)
                    db.flush()  # Get the user ID

                # Validate receipt to create subscription
                app_store_service.validate_receipt(receipt_data, str(user.id))
                db.commit()

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
                            "created_via_receipt": True,
                            "new_account": True
                        },
                        "subscription": subscription_status
                    }),
                    201,
                    "application/json"
                )

    except Exception as e:
        logger.exception("Failed to authenticate with receipt")
        return cors_response(
            json.dumps({
                "success": False,
                "message": "Internal server error"
            }),
            500,
            "application/json"
        )

@bp.function_name(name="LinkAccount")
@bp.route(route="auth/link_account", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def link_account(req: func.HttpRequest) -> func.HttpResponse:
    """
    Link an existing email/password account to an App Store subscription
    or upgrade an App Store-only account to have email/password access

    Expected payload:
    {
        "email": "user@example.com",
        "password": "password123",
        "receipt_data": "base64_encoded_receipt_data"
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()
        receipt_data = data.get("receipt_data")

        if not all([email, password, receipt_data]):
            return cors_response("Missing email, password, or receipt_data", 400)

        # Validate the receipt first
        success, apple_response = app_store_service._make_validation_request(
            app_store_service.PRODUCTION_URL,
            {
                "receipt-data": receipt_data,
                "password": app_store_service.app_store_password,
                "exclude-old-transactions": True
            }
        )

        if apple_response.get("status") == 21007:
            success, apple_response = app_store_service._make_validation_request(
                app_store_service.SANDBOX_URL,
                {
                    "receipt-data": receipt_data,
                    "password": app_store_service.app_store_password,
                    "exclude-old-transactions": True
                }
            )

        if not success or apple_response.get("status") != 0:
            return cors_response("Invalid receipt", 400)

        # Extract transaction info
        receipt = apple_response.get("receipt", {})
        latest_receipt_info = apple_response.get("latest_receipt_info", [])
        transactions = latest_receipt_info if latest_receipt_info else receipt.get("in_app", [])

        if not transactions:
            return cors_response("No valid transactions in receipt", 400)

        transaction = transactions[0]
        original_transaction_id = (
            transaction.get("original_transaction_id") or
            transaction.get("transaction_id")
        )

        with SessionLocal() as db:
            # Check if this email already exists
            existing_email_user = db.query(User).filter(User.email == email).first()

            # Check if App Store subscription already exists
            existing_subscription = db.query(UserSubscription).filter(
                UserSubscription.transaction_id == original_transaction_id,
                UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
            ).first()

            if existing_email_user and existing_subscription:
                # Both exist - check if they're the same user
                if existing_email_user.id == existing_subscription.user_id:
                    return cors_response("Account already linked", 400)
                else:
                    # Different users - need to merge accounts
                    return cors_response(
                        "Email already exists with different App Store account. Please contact support.",
                        409
                    )

            elif existing_email_user and not existing_subscription:
                # Email user exists, need to add App Store subscription
                from auth.utils import hash_password
                existing_email_user.password_hash = hash_password(password)

                # Validate receipt to create subscription for this user
                app_store_service.validate_receipt(receipt_data, str(existing_email_user.id))

                db.commit()

                token = create_access_token({"sub": str(existing_email_user.id)})
                subscription_status = app_store_service.get_user_subscription_status(str(existing_email_user.id))

                return cors_response(
                    json.dumps({
                        "success": True,
                        "message": "App Store subscription linked to existing account",
                        "access_token": token,
                        "token_type": "bearer",
                        "subscription": subscription_status
                    }),
                    200,
                    "application/json"
                )

            elif not existing_email_user and existing_subscription:
                # App Store user exists, upgrade to email/password
                from auth.utils import hash_password
                app_store_user = existing_subscription.user

                # Update the auto-generated email to the real email
                app_store_user.email = email
                app_store_user.password_hash = hash_password(password)
                app_store_user.created_via_receipt = True

                db.commit()

                token = create_access_token({"sub": str(app_store_user.id)})
                subscription_status = app_store_service.get_user_subscription_status(str(app_store_user.id))

                return cors_response(
                    json.dumps({
                        "success": True,
                        "message": "Account upgraded with email/password access",
                        "access_token": token,
                        "token_type": "bearer",
                        "subscription": subscription_status
                    }),
                    200,
                    "application/json"
                )

            else:
                # Neither exists - create new linked account
                from auth.utils import hash_password
                user = User(
                    email=email,
                    password_hash=hash_password(password),
                    created_via_receipt=True
                )
                db.add(user)
                db.flush()

                # Validate receipt to create subscription
                app_store_service.validate_receipt(receipt_data, str(user.id))
                db.commit()

                token = create_access_token({"sub": str(user.id)})
                subscription_status = app_store_service.get_user_subscription_status(str(user.id))

                return cors_response(
                    json.dumps({
                        "success": True,
                        "message": "New account created with App Store subscription",
                        "access_token": token,
                        "token_type": "bearer",
                        "subscription": subscription_status
                    }),
                    201,
                    "application/json"
                )

    except Exception as e:
        logger.exception("Failed to link account")
        return cors_response(
            json.dumps({
                "success": False,
                "message": "Internal server error"
            }),
            500,
            "application/json"
        )