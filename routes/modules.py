"""
Module and Coding API endpoints for manufacturer-specific ECU scanning and coding.
Cross-brand compatible architecture with VAG-specific coding support.
"""
import azure.functions as func
import json
import logging
from utils.cors import cors_response
from auth.deps import current_user_from_request
from services.module_service import (
    get_modules_for_manufacturer,
    get_coding_bits_for_module,
    parse_coding_bytes,
    report_discovered_module,
    seed_vag_modules,
    seed_vag_coding_bits,
    save_vehicle_modules,
    get_vehicle_modules,
    delete_vehicle_modules,
    save_module_dtcs,
    get_vehicle_dtcs,
    clear_vehicle_dtcs,
)
from models import ManufacturerGroup

logger = logging.getLogger(__name__)
bp = func.Blueprint()


@bp.function_name(name="ModulesByManufacturer")
@bp.route(route="modules/{manufacturer}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def modules_by_manufacturer(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get all known modules for a manufacturer.

    Query params:
    - platform: Filter by platform code (e.g., "MQB", "MLB")
    - vin: Optional VIN for model-specific filtering
    """
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

    platform = req.params.get("platform")

    try:
        modules = get_modules_for_manufacturer(manufacturer, platform)

        return cors_response(
            json.dumps({
                "manufacturer": manufacturer.value,
                "platform": platform,
                "modules": modules,
                "totalCount": len(modules),
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting modules by manufacturer")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="ModuleCodingBits")
@bp.route(route="modules/{manufacturer}/{address}/coding", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def module_coding_bits(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get known coding bit definitions for a specific module.

    Query params:
    - platform: Filter bits by platform
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    manufacturer_str = req.route_params.get("manufacturer", "").upper()
    address = req.route_params.get("address", "")

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    platform = req.params.get("platform")

    try:
        result = get_coding_bits_for_module(manufacturer, address, platform)

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting coding bits for module")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="ParseCoding")
@bp.route(route="modules/parse-coding", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def parse_coding(req: func.HttpRequest) -> func.HttpResponse:
    """
    Parse raw coding bytes and return labeled bits with current values.

    This is THE KEY endpoint - takes raw hex from vehicle and returns
    human-readable coding bit labels with their current ON/OFF states.

    Request body:
    {
        "manufacturer": "VAG",
        "moduleAddress": "17",
        "rawBytes": "0B0400000000",
        "vin": "WAUZZZ...",      // optional
        "platform": "MLB"         // optional
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    try:
        body = req.get_json()
    except Exception:
        return cors_response(
            json.dumps({"error": "Invalid JSON body"}),
            400,
            "application/json"
        )

    manufacturer_str = body.get("manufacturer", "").upper()
    module_address = body.get("moduleAddress")
    raw_bytes = body.get("rawBytes")
    vin = body.get("vin")
    platform = body.get("platform")

    if not module_address:
        return cors_response(
            json.dumps({"error": "moduleAddress is required"}),
            400,
            "application/json"
        )

    if not raw_bytes:
        return cors_response(
            json.dumps({"error": "rawBytes is required"}),
            400,
            "application/json"
        )

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    try:
        result = parse_coding_bytes(
            manufacturer=manufacturer,
            module_address=module_address,
            raw_bytes=raw_bytes,
            platform=platform,
        )

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error parsing coding bytes")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="ModuleDiscovered")
@bp.route(route="modules/discovered", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def module_discovered(req: func.HttpRequest) -> func.HttpResponse:
    """
    Report a discovered module from user's vehicle scan.
    Crowdsources module presence data across VIN prefixes.

    Request body:
    {
        "vin": "WAUZZZ8K9EA123456",
        "manufacturer": "VAG",
        "moduleAddress": "17",
        "isPresent": true,
        "partNumber": "8K0 920 930 A",
        "softwareVersion": "0350",
        "hardwareVersion": "H12",
        "codingValue": "0B0400000000",
        "deviceType": "VGate iCar Pro"
    }
    """
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
    manufacturer_str = body.get("manufacturer", "").upper()
    module_address = body.get("moduleAddress")
    is_present = body.get("isPresent", True)
    part_number = body.get("partNumber")
    software_version = body.get("softwareVersion")
    hardware_version = body.get("hardwareVersion")
    coding_value = body.get("codingValue")
    device_type = body.get("deviceType")

    if not vin:
        return cors_response(
            json.dumps({"error": "VIN is required"}),
            400,
            "application/json"
        )

    if not module_address:
        return cors_response(
            json.dumps({"error": "moduleAddress is required"}),
            400,
            "application/json"
        )

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    try:
        result = report_discovered_module(
            vin=vin,
            manufacturer=manufacturer,
            module_address=module_address,
            is_present=is_present,
            part_number=part_number,
            software_version=software_version,
            hardware_version=hardware_version,
            coding_value=coding_value,
            device_type=device_type,
            user_id=user_id,
        )

        return cors_response(
            json.dumps(result),
            201,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error reporting discovered module")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="ModuleSeed")
@bp.route(route="modules/seed", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def module_seed(req: func.HttpRequest) -> func.HttpResponse:
    """
    Seed VAG modules and coding bits into database.
    Admin only endpoint.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user or user.role.value != "ADMIN":
        return cors_response("Unauthorized", 401)

    try:
        modules_result = seed_vag_modules()
        bits_result = seed_vag_coding_bits()

        return cors_response(
            json.dumps({
                "modules": modules_result,
                "codingBits": bits_result,
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error seeding modules")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="ManufacturerCapabilities")
@bp.route(route="modules/capabilities/{manufacturer}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def manufacturer_capabilities(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get capabilities for a manufacturer (coding support, module count, etc.)
    """
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

    # Define capabilities per manufacturer
    capabilities = {
        ManufacturerGroup.VAG: {
            "supportsCoding": True,
            "supportsAdaptations": False,  # Future
            "supportsOutputTests": False,  # Future
            "supportsBasicSettings": False,  # Future
            "moduleCount": 50,  # Approximate
        },
        ManufacturerGroup.BMW: {
            "supportsCoding": False,  # Future
            "supportsAdaptations": False,
            "supportsOutputTests": False,
            "supportsBasicSettings": False,
            "moduleCount": 30,
        },
        ManufacturerGroup.MERCEDES: {
            "supportsCoding": False,
            "supportsAdaptations": False,
            "supportsOutputTests": False,
            "supportsBasicSettings": False,
            "moduleCount": 25,
        },
    }

    # Default for unsupported manufacturers
    default_caps = {
        "supportsCoding": False,
        "supportsAdaptations": False,
        "supportsOutputTests": False,
        "supportsBasicSettings": False,
        "moduleCount": 8,  # Standard OBD-II
    }

    caps = capabilities.get(manufacturer, default_caps)
    caps["manufacturer"] = manufacturer.value

    return cors_response(
        json.dumps(caps),
        200,
        "application/json"
    )


@bp.function_name(name="VehicleModulesSave")
@bp.route(route="vehicles/{vehicle_id}/modules", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_modules_save(req: func.HttpRequest) -> func.HttpResponse:
    """
    Save scanned modules for a vehicle.
    Persists module scan results for future sessions.

    Request body:
    {
        "manufacturer": "VAG",
        "modules": [
            {
                "address": "17",
                "name": "Instrument Cluster",
                "longName": "Dashboard / Instrument Cluster",
                "isPresent": true,
                "partNumber": "8K0 920 930 A",
                "softwareVersion": "0350",
                "hardwareVersion": "H12",
                "codingValue": "0B0400000000",
                "codingSupported": true
            }
        ]
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    try:
        body = req.get_json()
    except Exception:
        return cors_response(
            json.dumps({"error": "Invalid JSON body"}),
            400,
            "application/json"
        )

    manufacturer_str = body.get("manufacturer", "").upper()
    modules = body.get("modules", [])

    if not modules:
        return cors_response(
            json.dumps({"error": "modules array is required"}),
            400,
            "application/json"
        )

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    try:
        result = save_vehicle_modules(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
            manufacturer=manufacturer,
            modules=modules,
        )

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error saving vehicle modules")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="VehicleModulesGet")
@bp.route(route="vehicles/{vehicle_id}/modules", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_modules_get(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get saved modules for a vehicle.
    Returns previously scanned module data.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    try:
        modules = get_vehicle_modules(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
        )

        return cors_response(
            json.dumps({
                "vehicleId": vehicle_id,
                "modules": modules,
                "totalCount": len(modules),
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting vehicle modules")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="VehicleModulesDelete")
@bp.route(route="vehicles/{vehicle_id}/modules", methods=["DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_modules_delete(req: func.HttpRequest) -> func.HttpResponse:
    """
    Delete all modules for a vehicle (before rescan).
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    try:
        result = delete_vehicle_modules(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
        )

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error deleting vehicle modules")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="VehicleDTCsSave")
@bp.route(route="vehicles/{vehicle_id}/dtcs", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_dtcs_save(req: func.HttpRequest) -> func.HttpResponse:
    """
    Save DTCs read from a vehicle module.

    Request body:
    {
        "manufacturer": "VAG",
        "moduleAddress": "17",
        "moduleName": "Instrument Cluster",
        "dtcs": [
            {
                "code": "P0123",
                "status": "active",
                "description": "Throttle Position Sensor",
                "isActive": true,
                "isPending": false,
                "isPermanent": false
            }
        ]
    }
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    try:
        body = req.get_json()
    except Exception:
        return cors_response(
            json.dumps({"error": "Invalid JSON body"}),
            400,
            "application/json"
        )

    manufacturer_str = body.get("manufacturer", "").upper()
    module_address = body.get("moduleAddress")
    module_name = body.get("moduleName", f"Module {module_address}")
    dtcs = body.get("dtcs", [])

    if not module_address:
        return cors_response(
            json.dumps({"error": "moduleAddress is required"}),
            400,
            "application/json"
        )

    try:
        manufacturer = ManufacturerGroup(manufacturer_str)
    except ValueError:
        return cors_response(
            json.dumps({"error": f"Invalid manufacturer: {manufacturer_str}"}),
            400,
            "application/json"
        )

    try:
        result = save_module_dtcs(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
            manufacturer=manufacturer,
            module_address=module_address,
            module_name=module_name,
            dtcs=dtcs,
        )

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error saving vehicle DTCs")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="VehicleDTCsGet")
@bp.route(route="vehicles/{vehicle_id}/dtcs", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_dtcs_get(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get all DTCs for a vehicle.
    Query param: active_only=true (default) to filter to active codes only.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    active_only = req.params.get("active_only", "true").lower() == "true"

    try:
        dtcs = get_vehicle_dtcs(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
            active_only=active_only,
        )

        return cors_response(
            json.dumps({
                "vehicleId": vehicle_id,
                "dtcs": dtcs,
                "totalCount": len(dtcs),
            }),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error getting vehicle DTCs")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )


@bp.function_name(name="VehicleDTCsClear")
@bp.route(route="vehicles/{vehicle_id}/dtcs/clear", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def vehicle_dtcs_clear(req: func.HttpRequest) -> func.HttpResponse:
    """
    Mark DTCs as cleared for a vehicle.
    Optional: moduleAddress in body to clear only a specific module.
    """
    if req.method == "OPTIONS":
        return cors_response(204)

    user = current_user_from_request(req)
    if not user:
        return cors_response("Unauthorized", 401)

    vehicle_id = req.route_params.get("vehicle_id")
    if not vehicle_id:
        return cors_response(
            json.dumps({"error": "vehicle_id is required"}),
            400,
            "application/json"
        )

    module_address = None
    try:
        body = req.get_json()
        module_address = body.get("moduleAddress")
    except Exception:
        pass

    try:
        result = clear_vehicle_dtcs(
            vehicle_id=vehicle_id,
            user_id=str(user.id),
            module_address=module_address,
        )

        return cors_response(
            json.dumps(result),
            200,
            "application/json"
        )
    except Exception as e:
        logger.exception("Error clearing vehicle DTCs")
        return cors_response(
            json.dumps({"error": str(e)}),
            500,
            "application/json"
        )
