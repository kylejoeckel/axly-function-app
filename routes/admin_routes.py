import azure.functions as func
import json
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from db import SessionLocal
from models import User, UserRole, SubscriptionProduct
from services.stripe_service import stripe_service

logger = logging.getLogger(__name__)
bp = func.Blueprint()

@bp.function_name(name="CreateSubscriptionProduct")
@bp.route(route="admin/products", methods=["POST", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def create_subscription_product(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role != UserRole.ADMIN:
        return cors_response("Unauthorized", 403)

    try:
        data = req.get_json()
        product_id = data.get('product_id')
        stripe_price_id = data.get('stripe_price_id')
        name = data.get('name')
        description = data.get('description')
        billing_period = data.get('billing_period', 'monthly')
        billing_period_unit = data.get('billing_period_unit', 'month')
        popular = data.get('popular', False)
        recommended = data.get('recommended', False)
        savings_text = data.get('savings_text')
        trial_available = data.get('trial_available', False)
        sort_order = data.get('sort_order', 0)
        active = data.get('active', True)

        if not all([product_id, stripe_price_id, name]):
            return cors_response(
                json.dumps({"success": False, "error": "product_id, stripe_price_id, and name are required"}),
                400,
                "application/json"
            )

        try:
            stripe_price = stripe_service.get_price(stripe_price_id)
            if not stripe_price['active']:
                return cors_response(
                    json.dumps({"success": False, "error": "Stripe price is not active"}),
                    400,
                    "application/json"
                )
        except Exception as e:
            return cors_response(
                json.dumps({"success": False, "error": f"Invalid Stripe price ID: {str(e)}"}),
                400,
                "application/json"
            )

        with SessionLocal() as db:
            existing = db.query(SubscriptionProduct).filter(
                SubscriptionProduct.product_id == product_id
            ).first()

            if existing:
                return cors_response(
                    json.dumps({"success": False, "error": "Product with this ID already exists"}),
                    409,
                    "application/json"
                )

            product = SubscriptionProduct(
                product_id=product_id,
                stripe_price_id=stripe_price_id,
                name=name,
                description=description,
                billing_period=billing_period,
                billing_period_unit=billing_period_unit,
                popular=popular,
                recommended=recommended,
                savings_text=savings_text,
                trial_available=trial_available,
                sort_order=sort_order,
                active=active
            )
            db.add(product)
            db.commit()

            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Product created successfully",
                    "product_id": product_id
                }),
                201,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to create subscription product")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )

@bp.function_name(name="UpdateSubscriptionProduct")
@bp.route(route="admin/products/{product_id}", methods=["PUT", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def update_subscription_product(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role != UserRole.ADMIN:
        return cors_response("Unauthorized", 403)

    try:
        product_id = req.route_params.get('product_id')
        data = req.get_json()

        with SessionLocal() as db:
            product = db.query(SubscriptionProduct).filter(
                SubscriptionProduct.product_id == product_id
            ).first()

            if not product:
                return cors_response(
                    json.dumps({"success": False, "error": "Product not found"}),
                    404,
                    "application/json"
                )

            if 'stripe_price_id' in data:
                try:
                    stripe_price = stripe_service.get_price(data['stripe_price_id'])
                    if not stripe_price['active']:
                        return cors_response(
                            json.dumps({"success": False, "error": "Stripe price is not active"}),
                            400,
                            "application/json"
                        )
                    product.stripe_price_id = data['stripe_price_id']
                except Exception as e:
                    return cors_response(
                        json.dumps({"success": False, "error": f"Invalid Stripe price ID: {str(e)}"}),
                        400,
                        "application/json"
                    )

            if 'name' in data:
                product.name = data['name']
            if 'description' in data:
                product.description = data['description']
            if 'billing_period' in data:
                product.billing_period = data['billing_period']
            if 'billing_period_unit' in data:
                product.billing_period_unit = data['billing_period_unit']
            if 'popular' in data:
                product.popular = data['popular']
            if 'recommended' in data:
                product.recommended = data['recommended']
            if 'savings_text' in data:
                product.savings_text = data['savings_text']
            if 'trial_available' in data:
                product.trial_available = data['trial_available']
            if 'sort_order' in data:
                product.sort_order = data['sort_order']
            if 'active' in data:
                product.active = data['active']

            db.commit()

            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Product updated successfully"
                }),
                200,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to update subscription product")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )

@bp.function_name(name="DeleteSubscriptionProduct")
@bp.route(route="admin/products/{product_id}", methods=["DELETE", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def delete_subscription_product(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role != UserRole.ADMIN:
        return cors_response("Unauthorized", 403)

    try:
        product_id = req.route_params.get('product_id')

        with SessionLocal() as db:
            product = db.query(SubscriptionProduct).filter(
                SubscriptionProduct.product_id == product_id
            ).first()

            if not product:
                return cors_response(
                    json.dumps({"success": False, "error": "Product not found"}),
                    404,
                    "application/json"
                )

            product.active = False
            db.commit()

            return cors_response(
                json.dumps({
                    "success": True,
                    "message": "Product deactivated successfully"
                }),
                200,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to delete subscription product")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )

@bp.function_name(name="ListAllSubscriptionProducts")
@bp.route(route="admin/products", methods=["GET", "OPTIONS"],
          auth_level=func.AuthLevel.ANONYMOUS)
def list_all_subscription_products(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role != UserRole.ADMIN:
        return cors_response("Unauthorized", 403)

    try:
        with SessionLocal() as db:
            products = db.query(SubscriptionProduct).order_by(
                SubscriptionProduct.sort_order
            ).all()

            products_list = []
            for product in products:
                products_list.append({
                    "id": product.id,
                    "product_id": product.product_id,
                    "stripe_price_id": product.stripe_price_id,
                    "name": product.name,
                    "description": product.description,
                    "billing_period": product.billing_period,
                    "billing_period_unit": product.billing_period_unit,
                    "popular": product.popular,
                    "recommended": product.recommended,
                    "savings_text": product.savings_text,
                    "trial_available": product.trial_available,
                    "sort_order": product.sort_order,
                    "active": product.active,
                    "created_at": product.created_at.isoformat() if product.created_at else None,
                    "updated_at": product.updated_at.isoformat() if product.updated_at else None
                })

            return cors_response(
                json.dumps({
                    "success": True,
                    "products": products_list,
                    "total_count": len(products_list)
                }),
                200,
                "application/json"
            )

    except Exception as e:
        logger.exception("Failed to list subscription products")
        return cors_response(
            json.dumps({"success": False, "error": str(e)}),
            500,
            "application/json"
        )
