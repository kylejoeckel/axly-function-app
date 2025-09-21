import json
import logging
import base64
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from db import SessionLocal
from models import UserSubscription, ReceiptValidation, SubscriptionPlatform, SubscriptionStatus
import os

logger = logging.getLogger(__name__)

class AppStoreService:
    """Service for validating Apple App Store receipts and managing subscriptions"""

    # Apple's receipt validation endpoints
    PRODUCTION_URL = "https://buy.itunes.apple.com/verifyReceipt"
    SANDBOX_URL = "https://sandbox.itunes.apple.com/verifyReceipt"

    def __init__(self):
        self.app_store_password = os.getenv("APP_STORE_SHARED_SECRET")
        if not self.app_store_password:
            logger.warning("APP_STORE_SHARED_SECRET not configured - receipt validation will fail")

    def validate_receipt(self, receipt_data: str, user_id: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate an App Store receipt with Apple's servers

        Args:
            receipt_data: Base64 encoded receipt data from the app
            user_id: UUID of the user making the purchase

        Returns:
            Tuple of (success: bool, response_data: dict)
        """
        if not self.app_store_password:
            return False, {"error": "App Store shared secret not configured"}

        payload = {
            "receipt-data": receipt_data,
            "password": self.app_store_password,
            "exclude-old-transactions": True
        }

        # Try production first, then sandbox if receipt is from sandbox
        response_data = self._make_validation_request(self.PRODUCTION_URL, payload)

        # If production returns 21007, receipt is from sandbox
        if response_data.get("status") == 21007:
            logger.info("Receipt is from sandbox, retrying with sandbox URL")
            response_data = self._make_validation_request(self.SANDBOX_URL, payload)

        success = response_data.get("status") == 0

        # Log the validation attempt
        with SessionLocal() as db:
            validation = ReceiptValidation(
                platform=SubscriptionPlatform.APPLE_APP_STORE,
                receipt_data=receipt_data,
                validation_response=json.dumps(response_data),
                validation_status="success" if success else "failure"
            )
            db.add(validation)
            db.commit()
            validation_id = validation.id

        if success:
            self._process_successful_receipt(response_data, user_id, validation_id)

        return success, response_data

    def _make_validation_request(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP request to Apple's validation endpoint"""
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to validate receipt: {e}")
            return {"status": -1, "error": str(e)}
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from Apple")
            return {"status": -1, "error": "Invalid response format"}

    def _process_successful_receipt(self, apple_response: Dict[str, Any], user_id: str, validation_id: str):
        """Process a successfully validated receipt and update subscription status"""

        receipt = apple_response.get("receipt", {})
        latest_receipt_info = apple_response.get("latest_receipt_info", [])

        # For auto-renewable subscriptions, use latest_receipt_info
        # For non-renewing products, use in_app from receipt
        transactions = latest_receipt_info if latest_receipt_info else receipt.get("in_app", [])

        with SessionLocal() as db:
            for transaction in transactions:
                self._process_transaction(db, transaction, user_id, validation_id)
            db.commit()

    def _process_transaction(self, db, transaction: Dict[str, Any], user_id: str, validation_id: str):
        """Process a single transaction from the receipt"""

        transaction_id = transaction.get("transaction_id")
        original_transaction_id = transaction.get("original_transaction_id")
        product_id = transaction.get("product_id")

        if not all([transaction_id, product_id]):
            logger.warning(f"Invalid transaction data: missing required fields")
            return

        # Check if we already have this subscription
        existing = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id,
            UserSubscription.transaction_id == original_transaction_id or transaction_id,
            UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
        ).first()

        purchase_date = self._parse_apple_timestamp(transaction.get("purchase_date_ms"))
        expires_date = self._parse_apple_timestamp(transaction.get("expires_date_ms"))

        # Determine subscription status
        status = self._determine_subscription_status(transaction, expires_date)

        if existing:
            # Update existing subscription
            existing.status = status
            existing.expires_date = expires_date
            existing.last_validated_at = datetime.now(timezone.utc)
            existing.auto_renew_status = transaction.get("auto_renew_status") == "1"

            # Update validation record to link to subscription
            validation = db.query(ReceiptValidation).filter(
                ReceiptValidation.id == validation_id
            ).first()
            if validation:
                validation.user_subscription_id = existing.id

            logger.info(f"Updated existing subscription {existing.id} for user {user_id}")
        else:
            # Create new subscription
            subscription = UserSubscription(
                user_id=user_id,
                platform=SubscriptionPlatform.APPLE_APP_STORE,
                status=status,
                transaction_id=original_transaction_id or transaction_id,
                product_id=product_id,
                purchase_date=purchase_date,
                expires_date=expires_date,
                auto_renew_status=transaction.get("auto_renew_status") == "1",
                last_validated_at=datetime.now(timezone.utc)
            )
            db.add(subscription)
            db.flush()  # Get the ID

            # Update validation record to link to subscription
            validation = db.query(ReceiptValidation).filter(
                ReceiptValidation.id == validation_id
            ).first()
            if validation:
                validation.user_subscription_id = subscription.id

            logger.info(f"Created new subscription {subscription.id} for user {user_id}")

    def _parse_apple_timestamp(self, timestamp_ms: Optional[str]) -> Optional[datetime]:
        """Convert Apple's millisecond timestamp to datetime"""
        if not timestamp_ms:
            return None
        try:
            return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            return None

    def _determine_subscription_status(self, transaction: Dict[str, Any], expires_date: Optional[datetime]) -> SubscriptionStatus:
        """Determine subscription status based on transaction data"""

        # Check if it's a cancellation
        cancellation_date = transaction.get("cancellation_date_ms")
        if cancellation_date:
            return SubscriptionStatus.CANCELED

        # Check if expired
        if expires_date and expires_date < datetime.now(timezone.utc):
            return SubscriptionStatus.EXPIRED

        # Check if in grace period
        is_in_grace_period = transaction.get("is_in_grace_period") == "true"
        if is_in_grace_period:
            return SubscriptionStatus.GRACE_PERIOD

        # Check if in billing retry
        is_in_billing_retry_period = transaction.get("is_in_billing_retry_period") == "true"
        if is_in_billing_retry_period:
            return SubscriptionStatus.BILLING_RETRY

        # Default to active if not expired and not cancelled
        return SubscriptionStatus.ACTIVE

    def get_user_subscription_status(self, user_id: str) -> Dict[str, Any]:
        """Get current subscription status for a user"""

        with SessionLocal() as db:
            subscription = db.query(UserSubscription).filter(
                UserSubscription.user_id == user_id,
                UserSubscription.platform == SubscriptionPlatform.APPLE_APP_STORE
            ).order_by(UserSubscription.created_at.desc()).first()

            if not subscription:
                return {
                    "has_active_subscription": False,
                    "status": None,
                    "expires_date": None,
                    "product_id": None
                }

            is_active = subscription.status in [
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.GRACE_PERIOD,
                SubscriptionStatus.BILLING_RETRY
            ]

            return {
                "has_active_subscription": is_active,
                "status": subscription.status.value,
                "expires_date": subscription.expires_date.isoformat() if subscription.expires_date else None,
                "product_id": subscription.product_id,
                "auto_renew_status": subscription.auto_renew_status
            }

    def refresh_subscription_status(self, user_id: str, receipt_data: str) -> Tuple[bool, Dict[str, Any]]:
        """Refresh subscription status by re-validating the latest receipt"""
        return self.validate_receipt(receipt_data, user_id)

# Global instance
app_store_service = AppStoreService()