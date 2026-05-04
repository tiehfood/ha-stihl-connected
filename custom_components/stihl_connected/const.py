"""Constants for the STIHL Connected integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "stihl_connected"

# Bluetooth SIG company identifier for "Andreas STIHL AG & Co" — registered.
STIHL_MANUFACTURER_ID: Final = 0x03DD  # 989

# 16-bit STIHL service UUID (full form), reused for both discovery and SUOTA.
STIHL_SERVICE_UUID: Final = "0000fe43-0000-1000-8000-00805f9b34fb"

# (protocolId, productId) -> (family, label, vendor_model_string)
FAMILY_TABLE: Final[dict[tuple[int, int], tuple[str, str, str]]] = {
    (1, 1): ("SC1", "Smart Connector 1", "SC1"),
    (3, 2): ("ARX000", "Charger", "ARX000"),
    (3, 8): ("ARX000", "Charger MP1", "ARX000-MP1"),
    (4, 3): ("SC2A", "Smart Connector 2 A", "SC2A"),
    (5, 4): ("APX00", "AP Battery", "APX00"),
    (6, 5): ("BC2", "Battery", "BC2"),
    (6, 10): ("BC2", "Battery AP600S", "BC2-AP600S"),
    (6, 11): ("BC2", "Tool ARxL", "BC2-ARxL"),
    (8, 9): ("IC72V", "IC72V Device", "IC72V"),
    (9, 12): ("SC1MP", "Smart Connector 1.1", "SC1MP"),
}

# Protocols where productId is at byte 1 instead of byte 11.
V6_PROTOCOLS: Final = frozenset({6, 8, 9})
