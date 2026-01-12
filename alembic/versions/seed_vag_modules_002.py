"""seed_vag_modules_and_coding_bits

Revision ID: seed_vag_modules_002
Revises: add_module_tables_001
Create Date: 2026-01-12

Seeds the database with VAG module definitions and 147 coding bits.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

revision: str = 'seed_vag_modules_002'
down_revision: Union[str, Sequence[str], None] = 'add_module_tables_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ===========================================
    # Seed VAG Modules (35 modules)
    # ===========================================
    vag_modules = [
        # Core modules (present on most vehicles)
        ("01", "Engine", "Engine Control Module (ECM)", "7E0", True, 1),
        ("02", "Transmission", "Transmission Control Module (TCM)", "7E1", True, 2),
        ("03", "ABS/ESP", "ABS Brakes / ESP", "7E2", True, 3),
        ("08", "HVAC", "Auto HVAC / Climatronic", "708", True, 10),
        ("09", "Central Electronics", "Central Electronics (BCM)", "710", True, 5),
        ("15", "Airbag", "Airbag Control Module", "715", True, 4),
        ("16", "Steering Column", "Steering Column Electronics", "716", True, 20),
        ("17", "Instrument Cluster", "Dashboard / Instrument Cluster", "714", True, 6),
        ("19", "CAN Gateway", "CAN Gateway", "716", False, 7),
        # Comfort modules
        ("42", "Driver Door", "Driver Door Electronics", "72A", True, 30),
        ("44", "Steering Assist", "Power Steering", "72C", True, 25),
        ("46", "Central Comfort", "Central Comfort Module", "72E", True, 8),
        ("52", "Passenger Door", "Passenger Door Electronics", "734", True, 31),
        ("62", "Rear Left Door", "Rear Left Door Electronics", "73E", True, 32),
        ("72", "Rear Right Door", "Rear Right Door Electronics", "748", True, 33),
        # Lighting
        ("55", "Headlights", "Headlight Range / Leveling", "737", True, 15),
        ("39", "Right Headlight", "Right Headlight", "727", True, 16),
        ("4F", "Central Electronics 2", "Central Electronics 2", "72F", True, 17),
        # Infotainment
        ("56", "Radio", "Radio Module", "738", True, 40),
        ("57", "TV Tuner", "Television Tuner", "739", True, 41),
        ("5F", "Infotainment", "Information Electronics (MMI)", "73F", True, 9),
        ("47", "Sound System", "Sound System Control Module", "72F", True, 42),
        ("37", "Navigation", "Navigation", "725", True, 43),
        # Safety / Driver Assist
        ("13", "ACC", "Adaptive Cruise Control", "713", True, 50),
        ("A5", "Front Sensors", "Front Sensors (ACC)", "7A5", True, 51),
        ("76", "Parking Aid", "Park Distance Control", "74E", True, 52),
        ("6C", "Backup Camera", "Rear View Camera", "744", True, 53),
        # Other modules
        ("05", "Kessy", "Access/Start Authorization", "705", True, 60),
        ("22", "AWD", "All-Wheel Drive", "71E", True, 61),
        ("25", "Immobilizer", "Immobilizer", "71F", True, 62),
        ("34", "Level Control", "Air Suspension", "722", True, 63),
        ("36", "Driver Seat", "Driver Seat Memory", "724", True, 64),
        ("38", "Roof Electronics", "Roof Electronics", "726", True, 65),
        ("65", "Tire Pressure", "TPMS", "741", True, 66),
        ("69", "Trailer", "Trailer Module", "745", True, 67),
        ("71", "Battery", "Battery Management", "747", True, 68),
        ("75", "Telematics", "Telematics", "74B", True, 69),
        ("77", "Telephone", "Telephone Module", "74F", True, 70),
    ]

    for addr, name, long_name, can_id, coding_supported, priority in vag_modules:
        conn.execute(text("""
            INSERT INTO module_registry (manufacturer, address, name, long_name, can_id, coding_supported, priority)
            VALUES ('VAG', :addr, :name, :long_name, :can_id, :coding_supported, :priority)
            ON CONFLICT (manufacturer, address) DO UPDATE SET
                name = EXCLUDED.name,
                long_name = EXCLUDED.long_name,
                can_id = EXCLUDED.can_id,
                coding_supported = EXCLUDED.coding_supported,
                priority = EXCLUDED.priority
        """), {"addr": addr, "name": name, "long_name": long_name, "can_id": can_id,
               "coding_supported": coding_supported, "priority": priority})

    # ===========================================
    # Seed VAG Coding Bits (147 bits)
    # ===========================================
    coding_bits = [
        # Module 17 - Instrument Cluster (24 bits)
        ("17", 0, 0, "Needle Sweep", "Gauge staging animation on startup", "display", "safe"),
        ("17", 0, 1, "Seatbelt Warning", "Seatbelt reminder chime enabled", "safety", "caution"),
        ("17", 0, 2, "Seatbelt Chime Duration", "Extended seatbelt warning duration", "safety", "caution"),
        ("17", 0, 3, "Speed Warning", "Speed warning threshold enabled", "display", "safe"),
        ("17", 0, 4, "Speed Warning Gong", "Audible speed warning", "display", "safe"),
        ("17", 0, 5, "Door Open Warning", "Door ajar warning on cluster", "safety", "safe"),
        ("17", 0, 6, "Lights On Warning", "Headlights on warning chime", "display", "safe"),
        ("17", 0, 7, "Key In Warning", "Key in ignition warning", "display", "safe"),
        ("17", 1, 0, "Digital Speedometer", "Show digital speed in cluster", "display", "safe"),
        ("17", 1, 1, "Oil Temperature", "Show oil temp in display", "display", "safe"),
        ("17", 1, 2, "Coolant Temperature", "Show coolant temp numerically", "display", "safe"),
        ("17", 1, 3, "Boost Pressure", "Show turbo boost in display", "display", "safe"),
        ("17", 1, 4, "Lap Timer", "Enable lap timer function", "display", "safe"),
        ("17", 1, 5, "G-Meter Display", "Show G-force meter", "display", "safe"),
        ("17", 1, 6, "Efficiency Display", "Show fuel efficiency info", "display", "safe"),
        ("17", 1, 7, "Sport Display", "Show sport mode info", "display", "safe"),
        ("17", 2, 0, "Fuel Display Liters", "Show fuel remaining in liters", "display", "safe"),
        ("17", 2, 1, "Fuel Display Gallons", "Show fuel remaining in gallons", "display", "safe"),
        ("17", 2, 2, "Range Display", "Show estimated range", "display", "safe"),
        ("17", 2, 3, "Low Fuel Warning", "Low fuel distance warning", "display", "safe"),
        ("17", 2, 4, "Ambient Temperature", "Show outside temp in cluster", "display", "safe"),
        ("17", 2, 5, "Ice Warning", "Warning when temp below 4C", "safety", "safe"),
        ("17", 3, 0, "Service Interval", "Show service interval reminder", "display", "safe"),
        ("17", 3, 1, "Oil Change Reminder", "Oil change service reminder", "display", "safe"),

        # Module 09 - Central Electronics BCM (38 bits)
        ("09", 0, 0, "Auto Lock Speed", "Lock doors when driving over 15km/h", "comfort", "safe"),
        ("09", 0, 1, "Auto Unlock Park", "Unlock doors when shifted to Park", "comfort", "safe"),
        ("09", 0, 2, "Auto Unlock Key Out", "Unlock doors when key removed", "comfort", "safe"),
        ("09", 0, 3, "Selective Unlock", "First press unlocks driver only", "comfort", "safe"),
        ("09", 0, 4, "Auto Relock", "Relock if no door opened in 30s", "comfort", "safe"),
        ("09", 0, 5, "Double Lock", "Enable double-lock function", "safety", "caution"),
        ("09", 0, 6, "Remote Start", "Remote start capability", "comfort", "safe"),
        ("09", 0, 7, "Panic Alarm", "Panic alarm from key fob", "safety", "safe"),
        ("09", 1, 0, "Coming Home Lights", "Headlights stay on after exit", "lighting", "safe"),
        ("09", 1, 1, "Leaving Home Lights", "Headlights on when unlocking", "lighting", "safe"),
        ("09", 1, 2, "Coming Home Duration", "Extended coming home timer", "lighting", "safe"),
        ("09", 1, 3, "Pathway Lighting", "Ground lights on unlock", "lighting", "safe"),
        ("09", 1, 4, "Interior Light Delay", "Extended interior light delay", "lighting", "safe"),
        ("09", 1, 5, "Footwell Lighting", "Ambient footwell lights", "lighting", "safe"),
        ("09", 1, 6, "Ambient Lighting", "Interior ambient lighting", "lighting", "safe"),
        ("09", 1, 7, "Puddle Lights", "Door handle puddle lights", "lighting", "safe"),
        ("09", 2, 0, "DRL Active", "Daytime running lights enabled", "lighting", "safe"),
        ("09", 2, 1, "DRL Menu Option", "DRL on/off option in settings", "lighting", "safe"),
        ("09", 2, 2, "DRL via LED", "Use LED strips for DRL", "lighting", "safe"),
        ("09", 2, 3, "DRL with Low Beams", "DRL using low beam headlights", "lighting", "safe"),
        ("09", 2, 4, "Cornering Lights", "Fog lights aim into turns", "lighting", "safe"),
        ("09", 2, 5, "US Tail Lights", "Amber turns with US pattern", "lighting", "safe"),
        ("09", 2, 6, "Euro Tail Lights", "Red turns with Euro pattern", "lighting", "safe"),
        ("09", 2, 7, "Rear Fog as Brake", "Use rear fog as extra brake light", "lighting", "caution"),
        ("09", 3, 0, "Beep on Lock", "Chirp confirmation when locking", "comfort", "safe"),
        ("09", 3, 1, "Beep on Unlock", "Chirp confirmation when unlocking", "comfort", "safe"),
        ("09", 3, 2, "Flash on Lock", "Lights flash when locking", "comfort", "safe"),
        ("09", 3, 3, "Flash on Unlock", "Lights flash when unlocking", "comfort", "safe"),
        ("09", 3, 4, "Interior Light Lock", "Interior lights flash on lock", "comfort", "safe"),
        ("09", 4, 0, "Mirror Fold on Lock", "Fold mirrors when locking", "comfort", "safe"),
        ("09", 4, 1, "Mirror Unfold Unlock", "Unfold mirrors when unlocking", "comfort", "safe"),
        ("09", 4, 2, "Mirror Dip Reverse", "Dip passenger mirror in reverse", "comfort", "safe"),
        ("09", 4, 3, "Mirror Memory", "Mirror position memory", "comfort", "safe"),
        ("09", 4, 4, "Mirror Auto Dim", "Auto-dimming mirrors", "comfort", "safe"),
        ("09", 5, 0, "One Touch Windows", "One-touch up/down all windows", "comfort", "safe"),
        ("09", 5, 1, "Window Pinch Protect", "Anti-pinch for all windows", "safety", "safe"),

        # Module 46 - Central Comfort (15 bits)
        ("46", 0, 0, "Comfort Windows", "Windows from key fob hold", "comfort", "safe"),
        ("46", 0, 1, "Comfort Sunroof", "Sunroof from key fob hold", "comfort", "safe"),
        ("46", 0, 2, "Comfort Close All", "Close all windows and sunroof", "comfort", "safe"),
        ("46", 0, 3, "Comfort Open All", "Open all windows and sunroof", "comfort", "safe"),
        ("46", 0, 4, "Rain Close Windows", "Close windows on rain sensor", "comfort", "safe"),
        ("46", 0, 5, "Rain Close Sunroof", "Close sunroof on rain sensor", "comfort", "safe"),
        ("46", 0, 6, "Speed Close Windows", "Auto close windows at speed", "comfort", "safe"),
        ("46", 1, 0, "Hold Time Short", "Short key fob hold duration", "comfort", "safe"),
        ("46", 1, 1, "Hold Time Long", "Long key fob hold duration", "comfort", "safe"),
        ("46", 1, 2, "Interior Monitor", "Interior motion sensor active", "safety", "safe"),
        ("46", 1, 3, "Tilt Sensor", "Tilt/tow alarm sensor", "safety", "safe"),
        ("46", 2, 0, "Trunk Release Hold", "Hold to release trunk", "comfort", "safe"),
        ("46", 2, 1, "Easy Entry", "Seat/wheel move for entry", "comfort", "safe"),
        ("46", 2, 2, "Memory Seat Link", "Link seat to key memory", "comfort", "safe"),
        ("46", 2, 3, "Memory Mirror Link", "Link mirrors to key memory", "comfort", "safe"),

        # Module 55 - Headlight Range (12 bits)
        ("55", 0, 0, "DRL Active", "Daytime running lights enabled", "lighting", "safe"),
        ("55", 0, 1, "DRL 100%", "DRL at full brightness", "lighting", "safe"),
        ("55", 0, 2, "DRL 50%", "DRL at half brightness", "lighting", "safe"),
        ("55", 0, 3, "DRL via Position", "Use position lights for DRL", "lighting", "safe"),
        ("55", 0, 4, "DRL Turn Off", "DRL off when headlights on", "lighting", "safe"),
        ("55", 1, 0, "Auto Leveling", "Automatic headlight leveling", "lighting", "caution"),
        ("55", 1, 1, "Static Leveling", "Static headlight level", "lighting", "caution"),
        ("55", 1, 2, "Dynamic Leveling", "Dynamic headlight leveling", "lighting", "caution"),
        ("55", 1, 3, "Adaptive Light", "Adaptive cornering headlights", "lighting", "safe"),
        ("55", 1, 4, "Travel Mode", "Right-hand traffic mode", "lighting", "caution"),
        ("55", 2, 0, "Welcome Light", "Headlights on unlock", "lighting", "safe"),
        ("55", 2, 1, "Xenon Installed", "Xenon/LED headlights present", "lighting", "caution"),

        # Module 44 - Steering Assist (8 bits)
        ("44", 0, 0, "Sport Steering", "Sport steering weight feel", "performance", "safe"),
        ("44", 0, 1, "Comfort Steering", "Comfort steering weight", "performance", "safe"),
        ("44", 0, 2, "Lane Assist", "Lane keeping assist enabled", "safety", "caution"),
        ("44", 0, 3, "Lane Assist Vibration", "Steering vibration on lane departure", "safety", "caution"),
        ("44", 0, 4, "Speed Dependent", "Speed-dependent steering", "performance", "safe"),
        ("44", 1, 0, "Active Steering", "Active steering system", "performance", "caution"),
        ("44", 1, 1, "Park Assist Steering", "Parking assist control", "comfort", "safe"),
        ("44", 1, 2, "Dynamic Steering", "Dynamic steering ratio", "performance", "caution"),

        # Module 5F - Infotainment (15 bits)
        ("5F", 0, 0, "Video in Motion", "Allow video while driving", "other", "caution"),
        ("5F", 0, 1, "Nav in Motion", "Allow nav input while driving", "other", "caution"),
        ("5F", 0, 2, "Phone in Motion", "Allow phone input while driving", "other", "caution"),
        ("5F", 0, 3, "Bluetooth Audio", "Bluetooth audio streaming", "audio", "safe"),
        ("5F", 0, 4, "USB Video", "USB video playback", "other", "safe"),
        ("5F", 0, 5, "SD Card Support", "SD card media support", "audio", "safe"),
        ("5F", 1, 0, "Speed Lock Features", "Lock features at speed", "safety", "caution"),
        ("5F", 1, 1, "Voice Control", "Voice control enabled", "comfort", "safe"),
        ("5F", 1, 2, "CarPlay Enable", "Apple CarPlay support", "other", "safe"),
        ("5F", 1, 3, "Android Auto", "Android Auto support", "other", "safe"),
        ("5F", 1, 4, "MirrorLink", "MirrorLink support", "other", "safe"),
        ("5F", 2, 0, "Rear Camera Lines", "Show guidelines on camera", "display", "safe"),
        ("5F", 2, 1, "Rear Camera Delay", "Camera stays on longer", "display", "safe"),
        ("5F", 2, 2, "Top View Camera", "Birds eye view camera", "display", "safe"),
        ("5F", 2, 3, "Split Screen", "Split screen view", "display", "safe"),

        # Module 08 - HVAC Climatronic (10 bits)
        ("08", 0, 0, "Auto AC", "Automatic climate control", "comfort", "safe"),
        ("08", 0, 1, "Dual Zone", "Dual zone climate control", "comfort", "safe"),
        ("08", 0, 2, "Rear Climate", "Rear climate controls active", "comfort", "safe"),
        ("08", 0, 3, "Rest Heat", "Residual heat function", "comfort", "safe"),
        ("08", 0, 4, "AC Memory", "Remember AC settings", "comfort", "safe"),
        ("08", 1, 0, "Heated Seats Auto", "Auto heated seats with climate", "comfort", "safe"),
        ("08", 1, 1, "Cooled Seats Auto", "Auto ventilated seats", "comfort", "safe"),
        ("08", 1, 2, "Heated Wheel Auto", "Auto heated steering wheel", "comfort", "safe"),
        ("08", 1, 3, "Aux Heater", "Auxiliary heater enabled", "comfort", "safe"),
        ("08", 1, 4, "Defrost Priority", "Defrost takes priority", "comfort", "safe"),

        # Module 03 - ABS/ESP (8 bits)
        ("03", 0, 0, "ESP Active", "Electronic stability control on", "safety", "advanced"),
        ("03", 0, 1, "ESP Sport Mode", "ESP sport mode available", "performance", "caution"),
        ("03", 0, 2, "ASR Active", "Traction control active", "safety", "advanced"),
        ("03", 0, 3, "Hill Hold", "Hill hold assist enabled", "comfort", "safe"),
        ("03", 0, 4, "Auto Hold", "Auto brake hold at stops", "comfort", "safe"),
        ("03", 1, 0, "Brake Prefill", "Brake prefill on lift-off", "safety", "safe"),
        ("03", 1, 1, "Brake Assist", "Emergency brake assist", "safety", "caution"),
        ("03", 1, 2, "EBD Active", "Electronic brake distribution", "safety", "advanced"),

        # Module 02 - Transmission (8 bits)
        ("02", 0, 0, "Sport Mode", "Sport shifting mode", "performance", "safe"),
        ("02", 0, 1, "Manual Mode", "Manual/tiptronic mode", "performance", "safe"),
        ("02", 0, 2, "Launch Control", "Launch control enabled", "performance", "caution"),
        ("02", 0, 3, "Shift Paddles", "Paddle shifters active", "performance", "safe"),
        ("02", 1, 0, "Eco Mode", "Economy shifting mode", "performance", "safe"),
        ("02", 1, 1, "Kickdown Active", "Kickdown acceleration", "performance", "safe"),
        ("02", 1, 2, "Hill Mode", "Hill descent mode", "comfort", "safe"),
        ("02", 1, 3, "Neutral at Stop", "Shift to neutral at stop", "performance", "safe"),

        # Module 76 - Park Distance Control (6 bits)
        ("76", 0, 0, "Front Sensors", "Front parking sensors active", "safety", "safe"),
        ("76", 0, 1, "Rear Sensors", "Rear parking sensors active", "safety", "safe"),
        ("76", 0, 2, "Auto Enable Reverse", "Auto enable in reverse", "comfort", "safe"),
        ("76", 0, 3, "Visual Display", "Visual parking display", "display", "safe"),
        ("76", 0, 4, "Audio Warning", "Audio parking warning", "audio", "safe"),
        ("76", 0, 5, "Front Auto Enable", "Front sensors on slow speed", "comfort", "safe"),

        # Module 42 - Driver Door (6 bits)
        ("42", 0, 0, "One Touch Up", "One touch window up", "comfort", "safe"),
        ("42", 0, 1, "One Touch Down", "One touch window down", "comfort", "safe"),
        ("42", 0, 2, "Anti Pinch", "Anti-pinch protection", "safety", "safe"),
        ("42", 0, 3, "Mirror Heat", "Heated mirror installed", "comfort", "safe"),
        ("42", 0, 4, "Mirror Fold", "Power folding mirror", "comfort", "safe"),
        ("42", 0, 5, "Puddle Light", "Door puddle light", "lighting", "safe"),

        # Module 13 - Adaptive Cruise Control (6 bits)
        ("13", 0, 0, "ACC Active", "Adaptive cruise control", "safety", "caution"),
        ("13", 0, 1, "Stop and Go", "Stop and go traffic assist", "comfort", "caution"),
        ("13", 0, 2, "Follow Distance", "Adjustable follow distance", "comfort", "safe"),
        ("13", 0, 3, "Speed Limit Info", "Speed limit recognition", "display", "safe"),
        ("13", 0, 4, "Pre-Sense Brake", "Pre-sense emergency braking", "safety", "caution"),
        ("13", 0, 5, "Cross Traffic", "Cross traffic alert", "safety", "safe"),
    ]

    for module, byte_idx, bit_idx, name, desc, cat, safety in coding_bits:
        conn.execute(text("""
            INSERT INTO coding_bit_registry (manufacturer, module_address, byte_index, bit_index, name, description, category, safety_level, source)
            VALUES ('VAG', :module, :byte_idx, :bit_idx, :name, :desc, :cat, :safety, 'ross-tech-wiki')
            ON CONFLICT (manufacturer, module_address, byte_index, bit_index) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                category = EXCLUDED.category,
                safety_level = EXCLUDED.safety_level
        """), {"module": module, "byte_idx": byte_idx, "bit_idx": bit_idx,
               "name": name, "desc": desc, "cat": cat, "safety": safety})


def downgrade() -> None:
    conn = op.get_bind()
    # Remove seeded data
    conn.execute(text("DELETE FROM coding_bit_registry WHERE manufacturer = 'VAG'"))
    conn.execute(text("DELETE FROM module_registry WHERE manufacturer = 'VAG'"))
