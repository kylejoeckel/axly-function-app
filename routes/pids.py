import azure.functions as func
import json
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.pid_service import (
    get_manufacturer_group,
    get_pids_for_manufacturer,
    get_recommended_pids,
    get_pid_profile,
    report_discovered_pids,
    get_discovery_stats,
    seed_default_pids,
)
from models import ManufacturerGroup, PIDCategory

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.function_name(name="PIDProfile")
@bp.route(route="pids/profile", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def pid_profile(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    vin = req.params.get("vin")
    make = req.params.get("make")

    if not vin and not make:
        return cors_response(
            json.dumps({"error": "Either 'vin' or 'make' parameter required"}),
            400,
            "application/json"
        )

    manufacturer = get_manufacturer_group(make)

    try:
        result = get_recommended_pids(vin or "", manufacturer)

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting PID profile")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="PIDsByManufacturer")
@bp.route(route="pids/manufacturer/{manufacturer}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def pids_by_manufacturer(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    manufacturer_str = req.route_params.get("manufacturer", "").upper()

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    category_str = req.params.get("category")
    category = None
    if category_str:
        try:
            category = PIDCategory(category_str.lower())
        except ValueError:
            pass

    platform = req.params.get("platform")

    try:
        pids = get_pids_for_manufacturer(manufacturer, category, platform)

        return cors_response(
            json.dumps({
                "manufacturer": manufacturer.value,
                "category": category.value if category else None,
                "platform": platform,
                "pids": pids,
                "count": len(pids),
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting PIDs by manufacturer")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="PIDDiscovered")
@bp.route(route="pids/discovered", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def pid_discovered(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    user_id = user.id if user else None

    try:
        body = req.get_json()
    except Exception:
        return cors_response(
            json.dumps({"error": "Invalid JSON body"}),
            400,
            "application/json"
        )

    vin = body.get("vin")
    make = body.get("make")
    working_pids = body.get("workingPIDs", [])
    failed_pids = body.get("failedPIDs", [])
    device_type = body.get("deviceType")
    response_times = body.get("responseTimes")
    raw_responses = body.get("rawResponses")

    if not vin:
        return cors_response(
            json.dumps({"error": "VIN is required"}),
            400,
            "application/json"
        )

    if not working_pids and not failed_pids:
        return cors_response(
            json.dumps({"error": "At least one working or failed PID required"}),
            400,
            "application/json"
        )

    manufacturer = get_manufacturer_group(make)

    try:
        result = report_discovered_pids(
            vin=vin,
            manufacturer=manufacturer,
            working_pids=working_pids,
            failed_pids=failed_pids,
            device_type=device_type,
            user_id=user_id,
            response_times=response_times,
            raw_responses=raw_responses,
        )

        return cors_response(
            json.dumps(result),
            201,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error reporting discovered PIDs")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="PIDStats")
@bp.route(route="pids/stats", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def pid_stats(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    manufacturer_str = req.params.get("manufacturer")
    manufacturer = None

    if manufacturer_str:
        try:
            manufacturer = ManufacturerGroup(manufacturer_str.upper())
        except ValueError:
            pass

    try:
        stats = get_discovery_stats(manufacturer)

        return cors_response(
            json.dumps(stats),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting PID stats")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="PIDSeed")
@bp.route(route="pids/seed", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def pid_seed(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role.value != "ADMIN":
        return cors_response("Unauthorized", 401)

    try:
        result = seed_default_pids()

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error seeding PIDs")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )
