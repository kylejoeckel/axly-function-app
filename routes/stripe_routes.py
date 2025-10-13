import azure.functions as func
import json
import logging
from datetime import datetime
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.stripe_service import stripe_service
from db import SessionLocal
from models import User, StripeSubscription, UserTier

logger = logging.getLogger(__name__)
bp = func.Blueprint()

@bp.function_name(name="CreateCheckoutSession")
@bp.route(route="stripe/create-checkout", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def create_checkout_session(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        data = req.get_json()
        price_id = data.get('price_id')
        success_url = data.get('success_url', 'https://axly.pro/success')
        cancel_url = data.get('cancel_url', 'https://axly.pro/pricing')

        if not price_id:
            return cors_response(
                json.dumps({"success": False, "error": "price_id required"}),
                400,
                "application/json"
            )

        session = stripe_service.create_checkout_session(
            user_id=str(user.id),
            email=user.email,
            price_id=price_id,
            success_url=success_url,
            cancel_url=cancel_url
        )

        return cors_response(
            json.dumps({
                "success": True,
                "checkout_url": session.url,
                "session_id": session.id
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Failed to create checkout session")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )

@bp.function_name(name="CreatePortalSession")
@bp.route(route="stripe/create-portal", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def create_portal_session(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    try:
        with SessionLocal() as db:
            subscription = db.query(StripeSubscription).filter(
                StripeSubscription.user_id == user.id
            ).first()

            if not subscription or not subscription.stripe_customer_id:
                return cors_response(
                    json.dumps({"success": False, "error": "No subscription found"}),
                    404,
                    "application/json"
                )

            data = req.get_json()
            return_url = data.get('return_url', 'https://axly.pro/account')

            session = stripe_service.create_customer_portal_session(
                customer_id=subscription.stripe_customer_id,
                return_url=return_url
            )

            return cors_response(
                json.dumps({
                    "success": True,
                    "portal_url": session.url
                }),
                200,
                "application/json"
            )
    except Exception as e:
        logger.exception("Failed to create portal session")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )

@bp.function_name(name="StripeWebhook")
@bp.route(route="webhooks/stripe", methods=["POST"],
          auth_level=func.AuthLevel.ANONYMOUS)
def stripe_webhook(req: func.HttpRequest) -> func.HttpResponse:
    payload = req.get_body()
    sig_header = req.headers.get('stripe-signature')

    if not sig_header:
        logger.error("Missing stripe-signature header")
        return func.HttpResponse("Missing signature", status_code=400)

    try:
        event = stripe_service.verify_webhook_signature(payload, sig_header)
    except Exception as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return func.HttpResponse("Invalid signature", status_code=400)

    try:
        event_type = event['type']
        logger.info(f"Processing webhook event: {event_type}")

        if event_type == 'checkout.session.completed':
            handle_checkout_completed(event['data']['object'])
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(event['data']['object'])
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(event['data']['object'])
        elif event_type == 'invoice.payment_succeeded':
            handle_payment_succeeded(event['data']['object'])
        elif event_type == 'invoice.payment_failed':
            handle_payment_failed(event['data']['object'])
        else:
            logger.info(f"Unhandled event type: {event_type}")

        return func.HttpResponse("Success", status_code=200)
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return func.HttpResponse("Error", status_code=500)

def handle_checkout_completed(session):
    with SessionLocal() as db:
        try:
            user_id = session['metadata']['user_id']
            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                logger.error(f"User not found: {user_id}")
                return

            subscription_id = session.get('subscription')
            if not subscription_id:
                logger.error(f"No subscription ID in checkout session")
                return

            stripe_subscription = stripe_service.get_subscription(subscription_id)

            existing_sub = db.query(StripeSubscription).filter(
                StripeSubscription.user_id == user.id
            ).first()

            if existing_sub:
                existing_sub.stripe_customer_id = session['customer']
                existing_sub.stripe_subscription_id = subscription_id
                existing_sub.status = stripe_subscription['status']
                existing_sub.current_period_end = datetime.fromtimestamp(
                    stripe_subscription['current_period_end']
                )
                existing_sub.updated_at = datetime.utcnow()
            else:
                subscription = StripeSubscription(
                    user_id=user.id,
                    stripe_customer_id=session['customer'],
                    stripe_subscription_id=subscription_id,
                    status=stripe_subscription['status'],
                    current_period_end=datetime.fromtimestamp(
                        stripe_subscription['current_period_end']
                    )
                )
                db.add(subscription)

            user.tier = UserTier.PREMIUM
            db.commit()
            logger.info(f"Subscription created/updated for user {user_id}")

        except Exception as e:
            logger.exception(f"Error in handle_checkout_completed: {e}")
            db.rollback()

def handle_subscription_updated(subscription):
    with SessionLocal() as db:
        try:
            sub = db.query(StripeSubscription).filter(
                StripeSubscription.stripe_subscription_id == subscription['id']
            ).first()

            if sub:
                sub.status = subscription['status']
                sub.current_period_end = datetime.fromtimestamp(
                    subscription['current_period_end']
                )
                sub.updated_at = datetime.utcnow()

                if subscription['status'] == 'active':
                    user = db.query(User).filter(User.id == sub.user_id).first()
                    if user:
                        user.tier = UserTier.PREMIUM

                db.commit()
                logger.info(f"Subscription updated: {subscription['id']}")
            else:
                logger.warning(f"Subscription not found in DB: {subscription['id']}")

        except Exception as e:
            logger.exception(f"Error in handle_subscription_updated: {e}")
            db.rollback()

def handle_subscription_deleted(subscription):
    with SessionLocal() as db:
        try:
            sub = db.query(StripeSubscription).filter(
                StripeSubscription.stripe_subscription_id == subscription['id']
            ).first()

            if sub:
                sub.status = 'canceled'
                sub.updated_at = datetime.utcnow()

                user = db.query(User).filter(User.id == sub.user_id).first()
                if user:
                    user.tier = UserTier.FREE

                db.commit()
                logger.info(f"Subscription canceled: {subscription['id']}")
            else:
                logger.warning(f"Subscription not found in DB: {subscription['id']}")

        except Exception as e:
            logger.exception(f"Error in handle_subscription_deleted: {e}")
            db.rollback()

def handle_payment_succeeded(invoice):
    subscription_id = invoice.get('subscription')
    if subscription_id:
        logger.info(f"Payment succeeded for subscription: {subscription_id}")
        with SessionLocal() as db:
            try:
                sub = db.query(StripeSubscription).filter(
                    StripeSubscription.stripe_subscription_id == subscription_id
                ).first()

                if sub and sub.status != 'active':
                    sub.status = 'active'
                    sub.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Subscription reactivated: {subscription_id}")

            except Exception as e:
                logger.exception(f"Error in handle_payment_succeeded: {e}")
                db.rollback()

def handle_payment_failed(invoice):
    subscription_id = invoice.get('subscription')
    if subscription_id:
        logger.warning(f"Payment failed for subscription: {subscription_id}")
        with SessionLocal() as db:
            try:
                sub = db.query(StripeSubscription).filter(
                    StripeSubscription.stripe_subscription_id == subscription_id
                ).first()

                if sub:
                    sub.status = 'past_due'
                    sub.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(f"Subscription marked past_due: {subscription_id}")

            except Exception as e:
                logger.exception(f"Error in handle_payment_failed: {e}")
                db.rollback()
