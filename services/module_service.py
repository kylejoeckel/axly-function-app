"""
Module Service - Business logic for ECU module scanning and coding
"""
import logging
from typing import Optional, List, Dict, Any
from sqlalchemy import select
from db import get_session
from models.module import (
    ModuleRegistry,
    CodingBitRegistry,
    DiscoveredModule,
    CodingHistory,
    CodingCategory,
    CodingSafetyLevel,
)
from models.pid import ManufacturerGroup

logger = logging.getLogger(__name__)


def get_modules_for_manufacturer(
    manufacturer: ManufacturerGroup,
    platform: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get all module definitions for a manufacturer.
    Returns list of modules with their addresses and capabilities.
    """
    with get_session() as session:
        query = select(ModuleRegistry).where(
            ModuleRegistry.manufacturer == manufacturer,
            ModuleRegistry.is_active == True,
        )

        if platform:
            query = query.where(ModuleRegistry.platforms.contains([platform]))

        query = query.order_by(ModuleRegistry.priority, ModuleRegistry.address)
        results = session.execute(query).scalars().all()

        return [
            {
                "address": m.address,
                "name": m.name,
                "longName": m.long_name,
                "canId": m.can_id,
                "canIdResponse": m.can_id_response,
                "codingSupported": m.coding_supported,
                "codingDID": m.coding_did,
                "codingLength": m.coding_length,
                "platforms": m.platforms or [],
            }
            for m in results
        ]


def get_coding_bits_for_module(
    manufacturer: ManufacturerGroup,
    module_address: str,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get all known coding bit definitions for a specific module.
    """
    with get_session() as session:
        query = select(CodingBitRegistry).where(
            CodingBitRegistry.manufacturer == manufacturer,
            CodingBitRegistry.module_address == module_address,
        )

        if platform:
            query = query.where(
                (CodingBitRegistry.platforms == None) |
                (CodingBitRegistry.platforms.contains([platform]))
            )

        query = query.order_by(CodingBitRegistry.byte_index, CodingBitRegistry.bit_index)
        results = session.execute(query).scalars().all()

        # Get module name
        module = session.execute(
            select(ModuleRegistry).where(
                ModuleRegistry.manufacturer == manufacturer,
                ModuleRegistry.address == module_address,
            )
        ).scalar_one_or_none()

        module_name = module.name if module else f"Module {module_address}"

        bits = [
            {
                "byteIndex": b.byte_index,
                "bitIndex": b.bit_index,
                "name": b.name,
                "description": b.description,
                "category": b.category.value,
                "safetyLevel": b.safety_level.value,
                "platforms": b.platforms or [],
                "requires": b.requires or [],
                "conflicts": b.conflicts or [],
                "isVerified": b.is_verified,
            }
            for b in results
        ]

        return {
            "moduleAddress": module_address,
            "moduleName": module_name,
            "bits": bits,
            "totalBits": len(bits),
        }


def parse_coding_bytes(
    manufacturer: ManufacturerGroup,
    module_address: str,
    raw_bytes: str,
    platform: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse raw coding bytes and return labeled bits with current values.
    This is the main function that converts raw hex to readable coding data.
    """
    # Get bit definitions
    bit_data = get_coding_bits_for_module(manufacturer, module_address, platform)
    bit_defs = bit_data["bits"]

    # Convert hex string to bytes
    raw_bytes = raw_bytes.replace(" ", "").upper()
    try:
        byte_values = bytes.fromhex(raw_bytes)
    except ValueError:
        logger.error(f"Invalid hex string: {raw_bytes}")
        return {
            "moduleAddress": module_address,
            "moduleName": bit_data["moduleName"],
            "rawBytes": raw_bytes,
            "knownBits": [],
            "unknownBitCount": 0,
            "totalBits": 0,
            "error": "Invalid hex format",
        }

    # Parse each known bit
    known_bits = []
    for bit_def in bit_defs:
        byte_idx = bit_def["byteIndex"]
        bit_idx = bit_def["bitIndex"]

        if byte_idx < len(byte_values):
            current_value = bool((byte_values[byte_idx] >> bit_idx) & 1)
        else:
            current_value = False

        known_bits.append({
            **bit_def,
            "currentValue": current_value,
        })

    total_bits = len(byte_values) * 8
    unknown_bit_count = total_bits - len(known_bits)

    return {
        "moduleAddress": module_address,
        "moduleName": bit_data["moduleName"],
        "rawBytes": raw_bytes,
        "knownBits": known_bits,
        "unknownBitCount": unknown_bit_count,
        "totalBits": total_bits,
    }


def report_discovered_module(
    vin: str,
    manufacturer: ManufacturerGroup,
    module_address: str,
    is_present: bool,
    part_number: Optional[str] = None,
    software_version: Optional[str] = None,
    hardware_version: Optional[str] = None,
    coding_value: Optional[str] = None,
    device_type: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Report a discovered module from crowdsourced scanning.
    """
    vin_prefix = vin[:11] if len(vin) >= 11 else vin

    with get_session() as session:
        discovery = DiscoveredModule(
            vin=vin,
            vin_prefix=vin_prefix,
            manufacturer=manufacturer,
            module_address=module_address,
            is_present=is_present,
            part_number=part_number,
            software_version=software_version,
            hardware_version=hardware_version,
            coding_value=coding_value,
            device_type=device_type,
            reported_by=user_id,
        )
        session.add(discovery)
        session.commit()

        return {
            "success": True,
            "vinPrefix": vin_prefix,
            "moduleAddress": module_address,
        }


def save_coding_history(
    user_id: str,
    vehicle_id: str,
    manufacturer: ManufacturerGroup,
    module_address: str,
    coding_before: str,
    coding_after: str,
    changes: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """
    Save coding change to history for rollback support.
    """
    with get_session() as session:
        history = CodingHistory(
            user_id=user_id,
            vehicle_id=vehicle_id,
            manufacturer=manufacturer,
            module_address=module_address,
            coding_before=coding_before,
            coding_after=coding_after,
            changes=changes,
        )
        session.add(history)
        session.commit()

        return {
            "id": str(history.id),
            "moduleAddress": module_address,
            "codingBefore": coding_before,
            "codingAfter": coding_after,
        }


def seed_vag_modules() -> Dict[str, Any]:
    """
    Seed the database with VAG module definitions.
    Based on Ross-Tech VCDS documentation.
    """
    vag_modules = [
        # Core modules (present on most vehicles)
        {"address": "01", "name": "Engine", "long_name": "Engine Control Module (ECM)", "can_id": "7E0", "coding_supported": True, "priority": 1},
        {"address": "02", "name": "Transmission", "long_name": "Transmission Control Module (TCM)", "can_id": "7E1", "coding_supported": True, "priority": 2},
        {"address": "03", "name": "ABS/ESP", "long_name": "ABS Brakes / ESP", "can_id": "7E2", "coding_supported": True, "priority": 3},
        {"address": "08", "name": "HVAC", "long_name": "Auto HVAC / Climatronic", "can_id": "708", "coding_supported": True, "priority": 10},
        {"address": "09", "name": "Central Electronics", "long_name": "Central Electronics (BCM)", "can_id": "710", "coding_supported": True, "priority": 5},
        {"address": "15", "name": "Airbag", "long_name": "Airbag Control Module", "can_id": "715", "coding_supported": True, "priority": 4},
        {"address": "16", "name": "Steering Column", "long_name": "Steering Column Electronics", "can_id": "716", "coding_supported": True, "priority": 20},
        {"address": "17", "name": "Instrument Cluster", "long_name": "Dashboard / Instrument Cluster", "can_id": "714", "coding_supported": True, "priority": 6},
        {"address": "19", "name": "CAN Gateway", "long_name": "CAN Gateway", "can_id": "716", "coding_supported": False, "priority": 7},

        # Comfort modules
        {"address": "42", "name": "Driver Door", "long_name": "Driver Door Electronics", "can_id": "72A", "coding_supported": True, "priority": 30},
        {"address": "44", "name": "Steering Assist", "long_name": "Power Steering", "can_id": "72C", "coding_supported": True, "priority": 25},
        {"address": "46", "name": "Central Comfort", "long_name": "Central Comfort Module", "can_id": "72E", "coding_supported": True, "priority": 8},
        {"address": "52", "name": "Passenger Door", "long_name": "Passenger Door Electronics", "can_id": "734", "coding_supported": True, "priority": 31},
        {"address": "62", "name": "Rear Left Door", "long_name": "Rear Left Door Electronics", "can_id": "73E", "coding_supported": True, "priority": 32},
        {"address": "72", "name": "Rear Right Door", "long_name": "Rear Right Door Electronics", "can_id": "748", "coding_supported": True, "priority": 33},

        # Lighting
        {"address": "55", "name": "Headlights", "long_name": "Headlight Range / Leveling", "can_id": "737", "coding_supported": True, "priority": 15},
        {"address": "39", "name": "Right Headlight", "long_name": "Right Headlight", "can_id": "727", "coding_supported": True, "priority": 16},
        {"address": "4F", "name": "Central Electronics 2", "long_name": "Central Electronics 2", "can_id": "72F", "coding_supported": True, "priority": 17},

        # Infotainment
        {"address": "56", "name": "Radio", "long_name": "Radio Module", "can_id": "738", "coding_supported": True, "priority": 40},
        {"address": "57", "name": "TV Tuner", "long_name": "Television Tuner", "can_id": "739", "coding_supported": True, "priority": 41},
        {"address": "5F", "name": "Infotainment", "long_name": "Information Electronics (MMI)", "can_id": "73F", "coding_supported": True, "priority": 9},
        {"address": "47", "name": "Sound System", "long_name": "Sound System Control Module", "can_id": "72F", "coding_supported": True, "priority": 42},
        {"address": "37", "name": "Navigation", "long_name": "Navigation", "can_id": "725", "coding_supported": True, "priority": 43},

        # Safety / Driver Assist
        {"address": "13", "name": "ACC", "long_name": "Adaptive Cruise Control", "can_id": "713", "coding_supported": True, "priority": 50},
        {"address": "A5", "name": "Front Sensors", "long_name": "Front Sensors (ACC)", "can_id": "7A5", "coding_supported": True, "priority": 51},
        {"address": "76", "name": "Parking Aid", "long_name": "Park Distance Control", "can_id": "74E", "coding_supported": True, "priority": 52},
        {"address": "6C", "name": "Backup Camera", "long_name": "Rear View Camera", "can_id": "744", "coding_supported": True, "priority": 53},

        # Other modules
        {"address": "05", "name": "Kessy", "long_name": "Access/Start Authorization", "can_id": "705", "coding_supported": True, "priority": 60},
        {"address": "22", "name": "AWD", "long_name": "All-Wheel Drive", "can_id": "71E", "coding_supported": True, "priority": 61},
        {"address": "25", "name": "Immobilizer", "long_name": "Immobilizer", "can_id": "71F", "coding_supported": True, "priority": 62},
        {"address": "34", "name": "Level Control", "long_name": "Air Suspension", "can_id": "722", "coding_supported": True, "priority": 63},
        {"address": "36", "name": "Driver Seat", "long_name": "Driver Seat Memory", "can_id": "724", "coding_supported": True, "priority": 64},
        {"address": "38", "name": "Roof Electronics", "long_name": "Roof Electronics", "can_id": "726", "coding_supported": True, "priority": 65},
        {"address": "65", "name": "Tire Pressure", "long_name": "TPMS", "can_id": "741", "coding_supported": True, "priority": 66},
        {"address": "69", "name": "Trailer", "long_name": "Trailer Module", "can_id": "745", "coding_supported": True, "priority": 67},
        {"address": "71", "name": "Battery", "long_name": "Battery Management", "can_id": "747", "coding_supported": True, "priority": 68},
        {"address": "75", "name": "Telematics", "long_name": "Telematics", "can_id": "74B", "coding_supported": True, "priority": 69},
        {"address": "77", "name": "Telephone", "long_name": "Telephone Module", "can_id": "74F", "coding_supported": True, "priority": 70},
    ]

    with get_session() as session:
        created = 0
        updated = 0

        for m in vag_modules:
            existing = session.execute(
                select(ModuleRegistry).where(
                    ModuleRegistry.manufacturer == ManufacturerGroup.VAG,
                    ModuleRegistry.address == m["address"],
                )
            ).scalar_one_or_none()

            if existing:
                existing.name = m["name"]
                existing.long_name = m["long_name"]
                existing.can_id = m["can_id"]
                existing.coding_supported = m["coding_supported"]
                existing.priority = m["priority"]
                updated += 1
            else:
                module = ModuleRegistry(
                    manufacturer=ManufacturerGroup.VAG,
                    address=m["address"],
                    name=m["name"],
                    long_name=m["long_name"],
                    can_id=m["can_id"],
                    coding_supported=m["coding_supported"],
                    priority=m["priority"],
                )
                session.add(module)
                created += 1

        session.commit()

        return {
            "manufacturer": "VAG",
            "created": created,
            "updated": updated,
            "total": len(vag_modules),
        }


def seed_vag_coding_bits() -> Dict[str, Any]:
    """
    Seed the database with known VAG coding bits.
    Based on Ross-Tech Wiki and community documentation.
    """
    coding_bits = [
        # Module 17 - Instrument Cluster
        {"module": "17", "byte": 0, "bit": 0, "name": "Needle Sweep", "desc": "Gauge staging on startup", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 0, "bit": 1, "name": "Seatbelt Warning", "desc": "Seatbelt warning chime", "cat": "safety", "safety": "caution"},
        {"module": "17", "byte": 0, "bit": 3, "name": "Speed Warning", "desc": "Speed warning enabled", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 1, "bit": 0, "name": "Digital Speedometer", "desc": "Show digital speed in cluster", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 1, "bit": 2, "name": "Oil Temperature", "desc": "Show oil temp in display", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 1, "bit": 4, "name": "Lap Timer", "desc": "Enable lap timer function", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 2, "bit": 0, "name": "Fuel Display", "desc": "Show remaining fuel in liters", "cat": "display", "safety": "safe"},
        {"module": "17", "byte": 2, "bit": 3, "name": "Distance Warning", "desc": "Low fuel distance warning", "cat": "display", "safety": "safe"},

        # Module 09 - Central Electronics (BCM)
        {"module": "09", "byte": 0, "bit": 0, "name": "Auto Lock", "desc": "Lock doors when driving", "cat": "comfort", "safety": "safe"},
        {"module": "09", "byte": 0, "bit": 1, "name": "Auto Unlock", "desc": "Unlock doors when parked", "cat": "comfort", "safety": "safe"},
        {"module": "09", "byte": 1, "bit": 0, "name": "Coming Home", "desc": "Headlights stay on after exit", "cat": "lighting", "safety": "safe"},
        {"module": "09", "byte": 1, "bit": 1, "name": "Leaving Home", "desc": "Headlights on when unlocking", "cat": "lighting", "safety": "safe"},
        {"module": "09", "byte": 2, "bit": 0, "name": "DRL Menu", "desc": "DRL on/off option in settings", "cat": "lighting", "safety": "safe"},
        {"module": "09", "byte": 2, "bit": 4, "name": "Cornering Lights", "desc": "Fog lights aim into turns", "cat": "lighting", "safety": "safe"},
        {"module": "09", "byte": 3, "bit": 0, "name": "Beep on Lock", "desc": "Chirp when locking", "cat": "comfort", "safety": "safe"},
        {"module": "09", "byte": 3, "bit": 1, "name": "Beep on Unlock", "desc": "Chirp when unlocking", "cat": "comfort", "safety": "safe"},
        {"module": "09", "byte": 4, "bit": 0, "name": "Mirror Fold", "desc": "Mirrors fold on lock", "cat": "comfort", "safety": "safe"},

        # Module 46 - Central Comfort
        {"module": "46", "byte": 0, "bit": 0, "name": "Comfort Windows", "desc": "Windows from key fob", "cat": "comfort", "safety": "safe"},
        {"module": "46", "byte": 0, "bit": 1, "name": "Comfort Sunroof", "desc": "Sunroof from key fob", "cat": "comfort", "safety": "safe"},
        {"module": "46", "byte": 0, "bit": 4, "name": "Rain Close", "desc": "Close windows on rain sensor", "cat": "comfort", "safety": "safe"},
        {"module": "46", "byte": 1, "bit": 0, "name": "Hold Time", "desc": "Key fob hold duration", "cat": "comfort", "safety": "safe"},

        # Module 55 - Headlights
        {"module": "55", "byte": 0, "bit": 0, "name": "DRL Active", "desc": "Daytime running lights enabled", "cat": "lighting", "safety": "safe"},
        {"module": "55", "byte": 0, "bit": 2, "name": "DRL Brightness", "desc": "DRL brightness level", "cat": "lighting", "safety": "safe"},
        {"module": "55", "byte": 1, "bit": 0, "name": "Auto Leveling", "desc": "Automatic headlight leveling", "cat": "lighting", "safety": "caution"},
        {"module": "55", "byte": 1, "bit": 4, "name": "Adaptive Light", "desc": "Adaptive cornering lights", "cat": "lighting", "safety": "safe"},

        # Module 44 - Steering Assist
        {"module": "44", "byte": 0, "bit": 0, "name": "Sport Steering", "desc": "Sport steering weight", "cat": "performance", "safety": "safe"},
        {"module": "44", "byte": 0, "bit": 2, "name": "Lane Assist", "desc": "Lane keeping assist", "cat": "safety", "safety": "caution"},

        # Module 5F - Infotainment
        {"module": "5F", "byte": 0, "bit": 0, "name": "Video in Motion", "desc": "Allow video while driving", "cat": "other", "safety": "caution"},
        {"module": "5F", "byte": 1, "bit": 0, "name": "Speed Lock", "desc": "Lock features at speed", "cat": "safety", "safety": "caution"},
    ]

    category_map = {
        "comfort": CodingCategory.COMFORT,
        "lighting": CodingCategory.LIGHTING,
        "display": CodingCategory.DISPLAY,
        "safety": CodingCategory.SAFETY,
        "performance": CodingCategory.PERFORMANCE,
        "audio": CodingCategory.AUDIO,
        "other": CodingCategory.OTHER,
    }

    safety_map = {
        "safe": CodingSafetyLevel.SAFE,
        "caution": CodingSafetyLevel.CAUTION,
        "advanced": CodingSafetyLevel.ADVANCED,
    }

    with get_session() as session:
        created = 0
        updated = 0

        for b in coding_bits:
            existing = session.execute(
                select(CodingBitRegistry).where(
                    CodingBitRegistry.manufacturer == ManufacturerGroup.VAG,
                    CodingBitRegistry.module_address == b["module"],
                    CodingBitRegistry.byte_index == b["byte"],
                    CodingBitRegistry.bit_index == b["bit"],
                )
            ).scalar_one_or_none()

            if existing:
                existing.name = b["name"]
                existing.description = b["desc"]
                existing.category = category_map[b["cat"]]
                existing.safety_level = safety_map[b["safety"]]
                updated += 1
            else:
                bit = CodingBitRegistry(
                    manufacturer=ManufacturerGroup.VAG,
                    module_address=b["module"],
                    byte_index=b["byte"],
                    bit_index=b["bit"],
                    name=b["name"],
                    description=b["desc"],
                    category=category_map[b["cat"]],
                    safety_level=safety_map[b["safety"]],
                    source="ross-tech-wiki",
                )
                session.add(bit)
                created += 1

        session.commit()

        return {
            "manufacturer": "VAG",
            "created": created,
            "updated": updated,
            "total": len(coding_bits),
        }
