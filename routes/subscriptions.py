import azure.functions as func
import json
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from auth.token import create_access_token
from services.app_store_service import app_store_service
from db import SessionLocal
from models import User, UserSubscription, SubscriptionPlatform, StripeSubscription

logger = logging.getLogger(__name__)
bp = func.Blueprint()

@bp.function_name(name="ValidateReceipt")
@bp.route(route="subscriptions/validate_receipt", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def validate_receipt(req: func.HttpRequest) -> func.HttpResponse:
    """
    Validate App Store receipt and update subscription status.

    Validates the provided receipt with Apple's servers and updates
    the user's subscription status in the database.

    Args:
        req: HTTP request containing JSON with receipt_data and optional platform

    Returns:
        HTTP response with validation result and subscription status

    Raises:
        400: Missing receipt_data or unsupported platform
        401: Unauthorized
        500: Server error
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
    Get current subscription status for authenticated user.

    Retrieves the current subscription status including expiration date,
    product information, and renewal status.

    Args:
        req: HTTP request with Authorization header

    Returns:
        HTTP response with subscription status data

    Raises:
        401: Unauthorized
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        with SessionLocal() as db:
            stripe_sub = db.query(StripeSubscription).filter(
                StripeSubscription.user_id == user.id
            ).first()

            if stripe_sub:
                has_active = stripe_sub.status == 'active'
                return cors_response(
                    json.dumps({
                        "has_active_subscription": has_active,
                        "status": stripe_sub.status,
                        "expires_date": stripe_sub.current_period_end.isoformat(),
                        "product_id": "stripe_monthly",
                        "platform": "stripe",
                        "auto_renew_status": stripe_sub.status == 'active'
                    }),
                    200,
                    "application/json"
                )

            apple_status = app_store_service.get_user_subscription_status(str(user.id))
            return cors_response(
                json.dumps(apple_status),
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
    Refresh subscription status by re-validating receipt.

    Re-validates the user's latest receipt with Apple's servers
    to get the most current subscription status.

    Args:
        req: HTTP request containing JSON with receipt_data

    Returns:
        HTTP response with refreshed subscription status

    Raises:
        400: Missing receipt_data or validation failed
        401: Unauthorized
        500: Server error
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

@bp.function_name(name="GetSubscriptionProducts")
@bp.route(route="subscriptions/products", methods=["GET", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def get_subscription_products(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        from models import SubscriptionProduct
        from services.stripe_service import stripe_service

        with SessionLocal() as db:
            db_products = db.query(SubscriptionProduct).filter(
                SubscriptionProduct.active == True
            ).order_by(SubscriptionProduct.sort_order).all()

            products = []
            for db_product in db_products:
                try:
                    stripe_price = stripe_service.get_price(db_product.stripe_price_id)

                    amount = stripe_price['amount'] / 100
                    currency = stripe_price['currency'].upper()
                    currency_symbols = {'USD': '$', 'EUR': '€', 'GBP': '£'}
                    symbol = currency_symbols.get(currency, currency + ' ')

                    price_formatted = f"{symbol}{amount:.2f}"

                    product_data = {
                        "product_id": db_product.product_id,
                        "stripe_price_id": db_product.stripe_price_id,
                        "name": db_product.name,
                        "description": db_product.description,
                        "price": price_formatted,
                        "price_amount": amount,
                        "currency": currency,
                        "features": [
                            "Unlimited vehicle profiles",
                            "AI-powered diagnostic analysis",
                            "Conversational AI assistant",
                            "Live OBD2 data monitoring",
                            "Complete trouble code database",
                            "Service reminders & tracking",
                            "Priority customer support"
                        ],
                        "billing_period": db_product.billing_period,
                        "billing_period_unit": db_product.billing_period_unit,
                        "popular": db_product.popular,
                        "recommended": db_product.recommended,
                        "savings_text": db_product.savings_text,
                        "trial_available": db_product.trial_available,
                        "sort_order": db_product.sort_order
                    }
                    products.append(product_data)
                except Exception as e:
                    logger.error(f"Failed to fetch Stripe price for {db_product.product_id}: {e}")
                    continue

            return cors_response(
                json.dumps({
                    "success": True,
                    "products": products,
                    "total_count": len(products)
                }),
                200,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to get subscription products")
        return cors_response(
            json.dumps({
                "success": False,
                "message": "Failed to load subscription products",
                "products": []
            }),
            500,
            "application/json"
        )

@bp.function_name(name="AppStoreWebhook")
@bp.route(route="webhooks/app_store", methods=["POST"],
          auth_level=func.AuthLevel.ANONYMOUS)
def app_store_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Handle App Store Server Notifications.

    Receives and processes webhook notifications from Apple's App Store
    when subscription status changes occur.

    Args:
        req: HTTP request containing notification payload from Apple

    Returns:
        HTTP response acknowledging receipt

    Raises:
        500: Server error
    """
    try:
        raw_body = req.get_body()

        notification_data = json.loads(raw_body.decode('utf-8'))

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

        return func.HttpResponse("OK", status_code=200)

    except Exception as e:
        logger.exception("Failed to process App Store webhook")
        return func.HttpResponse("Error", status_code=500)

@bp.function_name(name="AuthWithReceipt")
@bp.route(route="auth/receipt", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def auth_with_receipt(req: func.HttpRequest) -> func.HttpResponse:
    """
    Authenticate user using App Store receipt.

    Subscription-first authentication that validates an App Store receipt
    and creates user account automatically if needed. Returns JWT token
    for immediate access.

    Args:
        req: HTTP request containing JSON with receipt_data and optional device_id

    Returns:
        HTTP response with access token and user data

    Raises:
        400: Missing receipt_data or invalid receipt
        401: Invalid receipt
        500: Server error
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        data = req.get_json()
        receipt_data = data.get("receipt_data")
        device_id = data.get("device_id")

        if not receipt_data:
            return cors_response("Missing receipt_data", 400)

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
            return cors_response(
                json.dumps({
                    "success": False,
                    "message": "Invalid receipt",
                    "apple_status": apple_response.get("status", "unknown")
                }),
                401,
                "application/json"
            )

        receipt = apple_response.get("receipt", {})
        latest_receipt_info = apple_response.get("latest_receipt_info", [])
        transactions = latest_receipt_info if latest_receipt_info else receipt.get("in_app", [])

        if not transactions:
            return cors_response("No valid transactions in receipt", 400)

        transaction = transactions[0] if transactions else None
        original_transaction_id = (
            transaction.get("original_transaction_id") or
            transaction.get("transaction_id")
        )

        if not original_transaction_id:
            return cors_response("Invalid transaction data", 400)

        with SessionLocal() as db:
            existing_subscription = db.query(UserSubscription).filter(
                UserSubscription.transaction_id == original_transaction_id,
                UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
            ).first()

            if existing_subscription:
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
                            "role": user.role.value,
                            "tier": user.tier.value,
                            "created_via_receipt": True
                        },
                        "subscription": subscription_status
                    }),
                    200,
                    "application/json"
                )
            else:
                auto_email = f"appstore_{original_transaction_id}@axly.app"

                existing_user = db.query(User).filter(User.email == auto_email).first()
                if existing_user:
                    user = existing_user
                else:
                    user = User(
                        email=auto_email,
                        password_hash="",
                        created_via_receipt=True
                    )
                    db.add(user)
                    db.flush()

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
                            "role": user.role.value,
                            "tier": user.tier.value,
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
    Link email/password account to App Store subscription.

    Links an existing email/password account to an App Store subscription
    or upgrades an App Store-only account to have email/password access.

    Args:
        req: HTTP request containing JSON with email, password, and receipt_data

    Returns:
        HTTP response with access token and link status

    Raises:
        400: Missing fields, invalid receipt, or account already linked
        409: Email exists with different App Store account
        500: Server error
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