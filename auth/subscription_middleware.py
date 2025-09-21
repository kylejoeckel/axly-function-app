from functools import wraps
from typing import Callable
import azure.functions as func
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.app_store_service import app_store_service
import json

def require_active_subscription(f: Callable) -> Callable:
    """
    Decorator that checks if user has an active subscription or is an admin
    Admins bypass subscription requirements, free tier users have limited access
    """
    @wraps(f)
    def decorated_function(req: func.HttpRequest) -> func.HttpResponse:
        # Handle OPTIONS requests
        if req.method == "OPTIONS":
            return f(req)

        # Get current user
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        # Admins bypass subscription check
        if user.is_admin:
            return f(req)

        # Free tier users don't need active subscription
        if user.is_free_tier:
            return f(req)

        # Premium users need active subscription
        if not user.requires_subscription:
            return f(req)

        # Check subscription status
        subscription_status = app_store_service.get_user_subscription_status(str(user.id))

        if not subscription_status.get("has_active_subscription", False):
            return cors_response(
                json.dumps({
                    "error": "Active subscription required",
                    "subscription_status": subscription_status
                }),
                402,  # Payment Required
                "application/json"
            )

        return f(req)

    return decorated_function

def require_premium_tier(f: Callable) -> Callable:
    """
    Decorator that requires premium tier access (for diagnose, spec sheets)
    """
    @wraps(f)
    def decorated_function(req: func.HttpRequest) -> func.HttpResponse:
        # Handle OPTIONS requests
        if req.method == "OPTIONS":
            return f(req)

        # Get current user
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        # Admins bypass tier check
        if user.is_admin:
            return f(req)

        # Check if user has premium access
        if not user.is_premium_tier:
            return cors_response(
                json.dumps({
                    "error": "Premium subscription required",
                    "current_tier": user.tier.value
                }),
                402,  # Payment Required
                "application/json"
            )

        # For premium users, check active subscription
        subscription_status = app_store_service.get_user_subscription_status(str(user.id))
        if not subscription_status.get("has_active_subscription", False):
            return cors_response(
                json.dumps({
                    "error": "Active premium subscription required",
                    "subscription_status": subscription_status
                }),
                402,  # Payment Required
                "application/json"
            )

        return f(req)

    return decorated_function

def admin_required(f: Callable) -> Callable:
    """
    Decorator that requires admin access
    """
    @wraps(f)
    def decorated_function(req: func.HttpRequest) -> func.HttpResponse:
        # Handle OPTIONS requests
        if req.method == "OPTIONS":
            return f(req)

        # Get current user
        user = current_user_from_request(req)
        if not user:
            return cors_response("Unauthorized", 401)

        # Check if user is admin
        if not user.is_admin:
            return cors_response("Admin access required", 403)

        return f(req)

    return decorated_function