import uuid
from typing import Optional, List, Dict, Any
from sqlalchemy import func as sql_func, and_, or_
from db import SessionLocal
from models import PIDRegistry, DiscoveredPID, PIDProfile, ManufacturerGroup, PIDCategory

VAG_MAKES = [
    "volkswagen", "vw", "audi", "porsche", "lamborghini",
    "bentley", "bugatti", "seat", "skoda", "cupra"
]

BMW_MAKES = ["bmw", "mini", "rolls-royce", "rolls royce"]
TOYOTA_MAKES = ["toyota", "lexus", "scion"]
GM_MAKES = ["chevrolet", "chevy", "gmc", "cadillac", "buick", "oldsmobile", "pontiac", "saturn", "hummer"]
FORD_MAKES = ["ford", "lincoln", "mercury"]
STELLANTIS_MAKES = ["chrysler", "dodge", "jeep", "ram", "fiat", "alfa romeo", "maserati", "peugeot", "citroen", "opel", "vauxhall"]
HONDA_MAKES = ["honda", "acura"]
NISSAN_MAKES = ["nissan", "infiniti", "datsun"]
HYUNDAI_MAKES = ["hyundai", "kia", "genesis"]
MERCEDES_MAKES = ["mercedes", "mercedes-benz", "smart", "maybach"]


def get_manufacturer_group(make: Optional[str]) -> ManufacturerGroup:
    if not make:
        return ManufacturerGroup.GENERIC

    normalized = make.lower().strip()

    if any(m in normalized for m in VAG_MAKES):
        return ManufacturerGroup.VAG
    if any(m in normalized for m in BMW_MAKES):
        return ManufacturerGroup.BMW
    if any(m in normalized for m in TOYOTA_MAKES):
        return ManufacturerGroup.TOYOTA
    if any(m in normalized for m in GM_MAKES):
        return ManufacturerGroup.GM
    if any(m in normalized for m in FORD_MAKES):
        return ManufacturerGroup.FORD
    if any(m in normalized for m in STELLANTIS_MAKES):
        return ManufacturerGroup.STELLANTIS
    if any(m in normalized for m in HONDA_MAKES):
        return ManufacturerGroup.HONDA
    if any(m in normalized for m in NISSAN_MAKES):
        return ManufacturerGroup.NISSAN
    if any(m in normalized for m in HYUNDAI_MAKES):
        return ManufacturerGroup.HYUNDAI
    if any(m in normalized for m in MERCEDES_MAKES):
        return ManufacturerGroup.MERCEDES

    return ManufacturerGroup.GENERIC


def get_vin_prefix(vin: str) -> str:
    if not vin or len(vin) < 8:
        return ""
    return vin[:8].upper()


def get_pids_for_manufacturer(
    manufacturer: ManufacturerGroup,
    category: Optional[PIDCategory] = None,
    platform: Optional[str] = None
) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        query = db.query(PIDRegistry).filter(
            PIDRegistry.is_active == True,
            or_(
                PIDRegistry.manufacturer == manufacturer,
                PIDRegistry.manufacturer == ManufacturerGroup.GENERIC
            )
        )

        if category:
            query = query.filter(PIDRegistry.category == category)

        if platform:
            query = query.filter(
                or_(
                    PIDRegistry.platform == None,
                    PIDRegistry.platform == platform
                )
            )

        pids = query.order_by(PIDRegistry.priority.asc()).all()

        return [
            {
                "id": p.pid_id,
                "name": p.name,
                "mode": p.mode,
                "pid": p.pid,
                "header": p.header,
                "formula": p.formula,
                "unit": p.unit,
                "min": p.min_value,
                "max": p.max_value,
                "bytes": p.bytes_count,
                "category": p.category.value if p.category else "engine",
                "priority": p.priority,
                "platform": p.platform,
            }
            for p in pids
        ]


def get_pid_profile(vin: str, manufacturer: ManufacturerGroup) -> Optional[Dict[str, Any]]:
    vin_prefix = get_vin_prefix(vin)
    if not vin_prefix:
        return None

    with SessionLocal() as db:
        profile = db.query(PIDProfile).filter(
            PIDProfile.vin_prefix == vin_prefix
        ).first()

        if profile:
            return {
                "vinPrefix": profile.vin_prefix,
                "manufacturer": profile.manufacturer.value,
                "platform": profile.platform,
                "boostPID": profile.boost_pid,
                "oilTempPID": profile.oil_temp_pid,
                "chargeAirTempPID": profile.charge_air_temp_pid,
                "transTempPID": profile.trans_temp_pid,
                "workingPIDs": profile.working_pids or [],
                "failedPIDs": profile.failed_pids or [],
                "sampleCount": profile.sample_count,
                "confidence": profile.confidence,
            }

    return None


def get_recommended_pids(
    vin: str,
    manufacturer: ManufacturerGroup
) -> Dict[str, Any]:
    vin_prefix = get_vin_prefix(vin)

    profile = get_pid_profile(vin, manufacturer)

    all_pids = get_pids_for_manufacturer(manufacturer)

    boost_pids = [p for p in all_pids if "boost" in p["id"].lower() or p["pid"] in ["70", "87", "6F"]]
    oil_temp_pids = [p for p in all_pids if "oil_temp" in p["id"].lower() or p["pid"] == "5C"]
    charge_air_pids = [p for p in all_pids if "charge_air" in p["id"].lower() or p["pid"] == "77"]

    if profile:
        working = set(profile.get("workingPIDs", []))
        failed = set(profile.get("failedPIDs", []))

        def prioritize(pids: List[Dict]) -> List[Dict]:
            working_first = [p for p in pids if p["id"] in working]
            unknown = [p for p in pids if p["id"] not in working and p["id"] not in failed]
            return working_first + unknown

        boost_pids = prioritize(boost_pids)
        oil_temp_pids = prioritize(oil_temp_pids)
        charge_air_pids = prioritize(charge_air_pids)

    return {
        "vinPrefix": vin_prefix,
        "manufacturer": manufacturer.value,
        "profile": profile,
        "boostPIDs": boost_pids,
        "oilTempPIDs": oil_temp_pids,
        "chargeAirTempPIDs": charge_air_pids,
        "allPIDs": all_pids,
    }


def report_discovered_pids(
    vin: str,
    manufacturer: ManufacturerGroup,
    working_pids: List[str],
    failed_pids: List[str],
    device_type: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    response_times: Optional[Dict[str, int]] = None,
    raw_responses: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    vin_prefix = get_vin_prefix(vin)
    if not vin_prefix:
        return {"error": "Invalid VIN"}

    with SessionLocal() as db:
        for pid_id in working_pids:
            discovery = DiscoveredPID(
                vin=vin.upper(),
                vin_prefix=vin_prefix,
                manufacturer=manufacturer,
                pid_id=pid_id,
                success=True,
                response_time_ms=response_times.get(pid_id) if response_times else None,
                raw_response=raw_responses.get(pid_id) if raw_responses else None,
                device_type=device_type,
                reported_by=user_id,
            )
            db.add(discovery)

        for pid_id in failed_pids:
            discovery = DiscoveredPID(
                vin=vin.upper(),
                vin_prefix=vin_prefix,
                manufacturer=manufacturer,
                pid_id=pid_id,
                success=False,
                device_type=device_type,
                reported_by=user_id,
            )
            db.add(discovery)

        db.commit()

        _update_pid_profile(db, vin_prefix, manufacturer, working_pids, failed_pids)

    return {
        "success": True,
        "vinPrefix": vin_prefix,
        "workingCount": len(working_pids),
        "failedCount": len(failed_pids),
    }


def _update_pid_profile(
    db,
    vin_prefix: str,
    manufacturer: ManufacturerGroup,
    new_working: List[str],
    new_failed: List[str]
):
    profile = db.query(PIDProfile).filter(
        PIDProfile.vin_prefix == vin_prefix
    ).first()

    if not profile:
        working_set = set(new_working)
        failed_set = set(new_failed)

        boost_pid = None
        oil_temp_pid = None
        charge_air_pid = None

        for pid_id in new_working:
            if "boost" in pid_id.lower() and not boost_pid:
                boost_pid = pid_id
            elif "oil_temp" in pid_id.lower() and not oil_temp_pid:
                oil_temp_pid = pid_id
            elif "charge_air" in pid_id.lower() and not charge_air_pid:
                charge_air_pid = pid_id

        profile = PIDProfile(
            vin_prefix=vin_prefix,
            manufacturer=manufacturer,
            boost_pid=boost_pid,
            oil_temp_pid=oil_temp_pid,
            charge_air_temp_pid=charge_air_pid,
            working_pids=list(working_set),
            failed_pids=list(failed_set - working_set),
            sample_count=1,
            confidence=0.5,
        )
        db.add(profile)
    else:
        existing_working = set(profile.working_pids or [])
        existing_failed = set(profile.failed_pids or [])

        new_working_set = existing_working.union(set(new_working))
        new_failed_set = existing_failed.union(set(new_failed)) - new_working_set

        for pid_id in new_working:
            if "boost" in pid_id.lower() and not profile.boost_pid:
                profile.boost_pid = pid_id
            elif "oil_temp" in pid_id.lower() and not profile.oil_temp_pid:
                profile.oil_temp_pid = pid_id
            elif "charge_air" in pid_id.lower() and not profile.charge_air_temp_pid:
                profile.charge_air_temp_pid = pid_id

        profile.working_pids = list(new_working_set)
        profile.failed_pids = list(new_failed_set)
        profile.sample_count += 1

        if profile.sample_count >= 10:
            profile.confidence = 0.95
        elif profile.sample_count >= 5:
            profile.confidence = 0.85
        elif profile.sample_count >= 3:
            profile.confidence = 0.75
        else:
            profile.confidence = 0.5 + (profile.sample_count * 0.1)

    db.commit()


def get_discovery_stats(manufacturer: Optional[ManufacturerGroup] = None) -> Dict[str, Any]:
    with SessionLocal() as db:
        query = db.query(DiscoveredPID)

        if manufacturer:
            query = query.filter(DiscoveredPID.manufacturer == manufacturer)

        total = query.count()
        successful = query.filter(DiscoveredPID.success == True).count()

        unique_vins = db.query(sql_func.count(sql_func.distinct(DiscoveredPID.vin_prefix))).scalar()

        top_working = db.query(
            DiscoveredPID.pid_id,
            sql_func.count(DiscoveredPID.id).label("count")
        ).filter(
            DiscoveredPID.success == True
        ).group_by(
            DiscoveredPID.pid_id
        ).order_by(
            sql_func.count(DiscoveredPID.id).desc()
        ).limit(10).all()

        return {
            "totalReports": total,
            "successfulReports": successful,
            "uniqueVehicles": unique_vins,
            "successRate": (successful / total * 100) if total > 0 else 0,
            "topWorkingPIDs": [{"pidId": p[0], "count": p[1]} for p in top_working],
        }


def seed_default_pids():
    default_pids = [
        {
            "pid_id": "boost_std_70",
            "name": "Boost Pressure",
            "manufacturer": ManufacturerGroup.GENERIC,
            "mode": "01",
            "pid": "70",
            "formula": "(A*256+B)/32",
            "unit": "kPa",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 1,
        },
        {
            "pid_id": "boost_std_87",
            "name": "Intake Manifold Pressure Enhanced",
            "manufacturer": ManufacturerGroup.GENERIC,
            "mode": "01",
            "pid": "87",
            "formula": "(A*256+B)/32",
            "unit": "kPa",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 2,
        },
        {
            "pid_id": "charge_air_temp_std",
            "name": "Charge Air Temp",
            "manufacturer": ManufacturerGroup.GENERIC,
            "mode": "01",
            "pid": "77",
            "formula": "A-40",
            "unit": "°C",
            "bytes_count": 1,
            "category": PIDCategory.ENGINE,
            "priority": 1,
        },
        {
            "pid_id": "oil_temp_std",
            "name": "Engine Oil Temp",
            "manufacturer": ManufacturerGroup.GENERIC,
            "mode": "01",
            "pid": "5C",
            "formula": "A-40",
            "unit": "°C",
            "bytes_count": 1,
            "category": PIDCategory.ENGINE,
            "priority": 1,
        },
        {
            "pid_id": "boost_uds_f40c",
            "name": "Boost Pressure UDS",
            "manufacturer": ManufacturerGroup.VAG,
            "mode": "22",
            "pid": "F40C",
            "header": "7E0",
            "formula": "(A*256+B)/32",
            "unit": "mbar",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 3,
        },
        {
            "pid_id": "boost_uds_2270",
            "name": "Boost Pressure MQB",
            "manufacturer": ManufacturerGroup.VAG,
            "platform": "MQB",
            "mode": "22",
            "pid": "2270",
            "header": "7E0",
            "formula": "(A*256+B)*0.01",
            "unit": "kPa",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 4,
        },
        {
            "pid_id": "boost_uds_31ce",
            "name": "Boost Pressure MLB",
            "manufacturer": ManufacturerGroup.VAG,
            "platform": "MLB",
            "mode": "22",
            "pid": "31CE",
            "header": "7E0",
            "formula": "(A*256+B)*0.001",
            "unit": "bar",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 5,
        },
        {
            "pid_id": "oil_temp_uds_vag",
            "name": "Oil Temperature",
            "manufacturer": ManufacturerGroup.VAG,
            "mode": "22",
            "pid": "2268",
            "header": "7E0",
            "formula": "A-40",
            "unit": "°C",
            "bytes_count": 1,
            "category": PIDCategory.ENGINE,
            "priority": 2,
        },
        {
            "pid_id": "charge_air_temp_uds_vag",
            "name": "Charge Air Temp",
            "manufacturer": ManufacturerGroup.VAG,
            "platform": "MQB",
            "mode": "22",
            "pid": "227A",
            "header": "7E0",
            "formula": "A-40",
            "unit": "°C",
            "bytes_count": 1,
            "category": PIDCategory.ENGINE,
            "priority": 2,
        },
        {
            "pid_id": "dpf_soot_mass_vag",
            "name": "DPF Soot Mass",
            "manufacturer": ManufacturerGroup.VAG,
            "mode": "22",
            "pid": "114F",
            "header": "7E0",
            "formula": "(A*256+B)*0.01",
            "unit": "g",
            "bytes_count": 2,
            "category": PIDCategory.ENGINE,
            "priority": 5,
        },
        {
            "pid_id": "trans_temp_std",
            "name": "Transmission Temp",
            "manufacturer": ManufacturerGroup.GENERIC,
            "mode": "01",
            "pid": "B4",
            "formula": "A-40",
            "unit": "°C",
            "bytes_count": 1,
            "category": PIDCategory.TRANSMISSION,
            "priority": 1,
        },
    ]

    with SessionLocal() as db:
        for pid_data in default_pids:
            existing = db.query(PIDRegistry).filter(
                PIDRegistry.pid_id == pid_data["pid_id"]
            ).first()

            if not existing:
                pid = PIDRegistry(**pid_data)
                db.add(pid)

        db.commit()

    return {"seeded": len(default_pids)}
