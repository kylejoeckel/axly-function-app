import stripe
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

class StripeService:
    def __init__(self):
        self.secret_key = os.getenv('STRIPE_SECRET_KEY')
        self.webhook_secret = os.getenv('STRIPE_WEBHOOK_SECRET')

        if not self.secret_key:
            logger.warning("STRIPE_SECRET_KEY not set")

    def create_checkout_session(self, user_id: str, email: str, price_id: str, success_url: str, cancel_url: str):
        try:
            session = stripe.checkout.Session.create(
                customer_email=email,
                payment_method_types=['card'],
                line_items=[{
                    'price': price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    'user_id': user_id,
                },
                allow_promotion_codes=True,
            )
            logger.info(f"Created checkout session for user {user_id}")
            return session
        except Exception as e:
            logger.error(f"Failed to create checkout session: {e}")
            raise

    def create_customer_portal_session(self, customer_id: str, return_url: str):
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            logger.info(f"Created portal session for customer {customer_id}")
            return session
        except Exception as e:
            logger.error(f"Failed to create portal session: {e}")
            raise

    def get_subscription(self, subscription_id: str):
        try:
            return stripe.Subscription.retrieve(subscription_id)
        except Exception as e:
            logger.error(f"Failed to retrieve subscription {subscription_id}: {e}")
            raise

    def get_customer(self, customer_id: str):
        try:
            return stripe.Customer.retrieve(customer_id)
        except Exception as e:
            logger.error(f"Failed to retrieve customer {customer_id}: {e}")
            raise

    def cancel_subscription(self, subscription_id: str):
        try:
            subscription = stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )
            logger.info(f"Subscription {subscription_id} set to cancel at period end")
            return subscription
        except Exception as e:
            logger.error(f"Failed to cancel subscription {subscription_id}: {e}")
            raise

    def verify_webhook_signature(self, payload: bytes, signature: str):
        if not self.webhook_secret:
            logger.error("STRIPE_WEBHOOK_SECRET not configured")
            raise ValueError("Webhook secret not configured")

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, self.webhook_secret
            )
            return event
        except ValueError as e:
            logger.error(f"Invalid webhook payload: {e}")
            raise
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            raise

    def get_price(self, price_id: str):
        try:
            price = stripe.Price.retrieve(price_id)
            return {
                'id': price.id,
                'amount': price.unit_amount,
                'currency': price.currency,
                'recurring': {
                    'interval': price.recurring.interval if price.recurring else None,
                    'interval_count': price.recurring.interval_count if price.recurring else None,
                },
                'product': price.product,
                'active': price.active
            }
        except Exception as e:
            logger.error(f"Failed to retrieve price {price_id}: {e}")
            raise

    def get_product(self, product_id: str):
        try:
            product = stripe.Product.retrieve(product_id)
            return {
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'active': product.active,
                'metadata': product.metadata
            }
        except Exception as e:
            logger.error(f"Failed to retrieve product {product_id}: {e}")
            raise

stripe_service = StripeService()
