import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from db import SessionLocal
from models import (
    AppStoreNotification,
    UserSubscription,
    SubscriptionPlatform,
    SubscriptionStatus
)

logger = logging.getLogger(__name__)

class AppStoreWebhookProcessor:
    """Process App Store Server Notifications to update subscription status"""

    def process_pending_notifications(self):
        """Process all unprocessed notifications"""
        with SessionLocal() as db:
            notifications = db.query(AppStoreNotification).filter(
                AppStoreNotification.processed == False
            ).order_by(AppStoreNotification.created_at).all()

            for notification in notifications:
                try:
                    self._process_notification(db, notification)
                    notification.processed = True
                    notification.processed_at = datetime.now(timezone.utc)
                    logger.info(f"Processed notification {notification.id}")
                except Exception as e:
                    logger.error(f"Failed to process notification {notification.id}: {e}")
                    # Don't mark as processed if it failed

            db.commit()

    def _process_notification(self, db, notification: AppStoreNotification):
        """Process a single App Store notification"""

        try:
            payload = json.loads(notification.raw_payload)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in notification {notification.id}")
            return

        notification_type = notification.notification_type

        # Extract transaction info
        latest_receipt_info = payload.get("latest_receipt_info")
        auto_renew_status_change_date_ms = payload.get("auto_renew_status_change_date_ms")
        auto_renew_status = payload.get("auto_renew_status")

        if not latest_receipt_info:
            logger.warning(f"No latest_receipt_info in notification {notification.id}")
            return

        # Find the user subscription based on transaction ID
        original_transaction_id = (
            latest_receipt_info.get("original_transaction_id") or
            latest_receipt_info.get("transaction_id")
        )

        if not original_transaction_id:
            logger.warning(f"No transaction ID in notification {notification.id}")
            return

        subscription = db.query(UserSubscription).filter(
            UserSubscription.transaction_id == original_transaction_id,
            UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
        ).first()

        if not subscription:
            logger.warning(f"No subscription found for transaction {original_transaction_id}")
            return

        # Process based on notification type
        if notification_type == "INITIAL_BUY":
            self._handle_initial_buy(subscription, latest_receipt_info)

        elif notification_type == "DID_RENEW":
            self._handle_renewal(subscription, latest_receipt_info)

        elif notification_type == "DID_FAIL_TO_RENEW":
            self._handle_renewal_failure(subscription, latest_receipt_info)

        elif notification_type == "DID_CANCEL":
            self._handle_cancellation(subscription, latest_receipt_info)

        elif notification_type == "DID_RECOVER":
            self._handle_recovery(subscription, latest_receipt_info)

        elif notification_type == "RENEWAL_EXTENDED":
            self._handle_renewal_extension(subscription, latest_receipt_info)

        elif notification_type == "REVOKE":
            self._handle_revocation(subscription, latest_receipt_info)

        else:
            logger.info(f"Unhandled notification type: {notification_type}")

        # Update auto-renew status if provided
        if auto_renew_status is not None:
            subscription.auto_renew_status = auto_renew_status == "true"

        subscription.last_validated_at = datetime.now(timezone.utc)

    def _handle_initial_buy(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle INITIAL_BUY notification"""
        subscription.status = SubscriptionStatus.ACTIVE
        expires_date = self._parse_apple_timestamp(receipt_info.get("expires_date_ms"))
        if expires_date:
            subscription.expires_date = expires_date
        logger.info(f"Initial purchase for subscription {subscription.id}")

    def _handle_renewal(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle DID_RENEW notification"""
        subscription.status = SubscriptionStatus.ACTIVE
        expires_date = self._parse_apple_timestamp(receipt_info.get("expires_date_ms"))
        if expires_date:
            subscription.expires_date = expires_date
        logger.info(f"Subscription renewed: {subscription.id}")

    def _handle_renewal_failure(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle DID_FAIL_TO_RENEW notification"""
        # Check if it's in grace period or billing retry
        is_in_grace_period = receipt_info.get("is_in_grace_period") == "true"
        is_in_billing_retry = receipt_info.get("is_in_billing_retry_period") == "true"

        if is_in_grace_period:
            subscription.status = SubscriptionStatus.GRACE_PERIOD
        elif is_in_billing_retry:
            subscription.status = SubscriptionStatus.BILLING_RETRY
        else:
            subscription.status = SubscriptionStatus.EXPIRED

        logger.info(f"Subscription renewal failed: {subscription.id}, status: {subscription.status}")

    def _handle_cancellation(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle DID_CANCEL notification"""
        subscription.status = SubscriptionStatus.CANCELED
        subscription.auto_renew_status = False
        logger.info(f"Subscription cancelled: {subscription.id}")

    def _handle_recovery(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle DID_RECOVER notification (billing issue resolved)"""
        subscription.status = SubscriptionStatus.ACTIVE
        expires_date = self._parse_apple_timestamp(receipt_info.get("expires_date_ms"))
        if expires_date:
            subscription.expires_date = expires_date
        logger.info(f"Subscription recovered: {subscription.id}")

    def _handle_renewal_extension(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle RENEWAL_EXTENDED notification"""
        expires_date = self._parse_apple_timestamp(receipt_info.get("expires_date_ms"))
        if expires_date:
            subscription.expires_date = expires_date
        logger.info(f"Subscription extended: {subscription.id}")

    def _handle_revocation(self, subscription: UserSubscription, receipt_info: Dict[str, Any]):
        """Handle REVOKE notification (refund issued)"""
        subscription.status = SubscriptionStatus.CANCELED
        logger.info(f"Subscription revoked (refunded): {subscription.id}")

    def _parse_apple_timestamp(self, timestamp_ms: Optional[str]) -> Optional[datetime]:
        """Convert Apple's millisecond timestamp to datetime"""
        if not timestamp_ms:
            return None
        try:
            return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            return None

# Global instance
webhook_processor = AppStoreWebhookProcessor()