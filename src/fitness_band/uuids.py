"""Bluetooth UUIDs and device-name patterns observed on the Huawei Band 9.

All UUIDs are 128-bit strings. The helper :func:`u` expands short 16-bit
Bluetooth SIG UUIDs (for example ``"180d"``) into the standard base UUID.
"""

from __future__ import annotations

BASE_UUID = "0000{short}-0000-1000-8000-00805f9b34fb"

# --- Standard Bluetooth SIG services / characteristics ---------------------
GAP_SERVICE = "00001800-0000-1000-8000-00805f9b34fb"
GATT_SERVICE = "00001801-0000-1000-8000-00805f9b34fb"
DEVICE_INFORMATION_SERVICE = "0000180a-0000-1000-8000-00805f9b34fb"
HEART_RATE_SERVICE = "0000180d-0000-1000-8000-00805f9b34fb"
BATTERY_SERVICE = "0000180f-0000-1000-8000-00805f9b34fb"
HUMAN_INTERFACE_DEVICE_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"

DEVICE_NAME = "00002a00-0000-1000-8000-00805f9b34fb"
APPEARANCE = "00002a01-0000-1000-8000-00805f9b34fb"
PERIPHERAL_PREFERRED_CONNECTION_PARAMETERS = "00002a04-0000-1000-8000-00805f9b34fb"

MANUFACTURER_NAME = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER = "00002a25-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION = "00002a26-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION = "00002a27-0000-1000-8000-00805f9b34fb"
SOFTWARE_REVISION = "00002a28-0000-1000-8000-00805f9b34fb"

HEART_RATE_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
BODY_SENSOR_LOCATION = "00002a38-0000-1000-8000-00805f9b34fb"
HEART_RATE_CONTROL_POINT = "00002a39-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"

CLIENT_CHARACTERISTIC_CONFIGURATION = "00002902-0000-1000-8000-00805f9b34fb"

# --- Huawei proprietary GATT ------------------------------------------------
# Main Huawei Link Protocol (LPv2/LPv3-style) transport.
HUAWEI_SERVICE = "0000fe86-0000-1000-8000-00805f9b34fb"
HUAWEI_WRITE = "0000fe01-0000-1000-8000-00805f9b34fb"
HUAWEI_READ = "0000fe02-0000-1000-8000-00805f9b34fb"

# Secondary vendor services observed on the Band 9. Their exact role is not
# confirmed yet; they are listed so reconnaissance output is stable.
HUAWEI_VENDOR_3802_SERVICE = "00003802-0000-1000-8000-00805f9b34fb"
HUAWEI_VENDOR_3802_CHAR = "00004a02-0000-1000-8000-00805f9b34fb"

HUAWEI_VENDOR_E2CB_SERVICE = "0000e2cb-0000-1000-8000-00805f9b34fb"
HUAWEI_VENDOR_E2CB_WRITE = "0000e914-0000-1000-8000-00805f9b34fb"
HUAWEI_VENDOR_E2CB_NOTIFY = "00001a19-0000-1000-8000-00805f9b34fb"

HUAWEI_VENDOR_E2E3_SERVICE = "0000e2e3-0000-1000-8000-00805f9b34fb"
HUAWEI_VENDOR_E2E3_WRITE = "0000e2e4-0000-1000-8000-00805f9b34fb"
HUAWEI_VENDOR_E2E3_NOTIFY = "0000e2e5-0000-1000-8000-00805f9b34fb"

HUAWEI_VENDOR_CC35_SERVICE = "cc353442-be58-4ea2-876e-11d8d6976366"
HUAWEI_VENDOR_CC35_CHAR = "c551c36a-0377-4a29-9657-74ffb655a188"

HUAWEI_SDP_SERVICE = "82ff3820-8411-400c-b85a-55bdb32cf060"

SERVICE_NAMES = {
    GAP_SERVICE: "Generic Access Profile",
    GATT_SERVICE: "Generic Attribute Profile",
    DEVICE_INFORMATION_SERVICE: "Device Information",
    HEART_RATE_SERVICE: "Heart Rate",
    BATTERY_SERVICE: "Battery",
    HUMAN_INTERFACE_DEVICE_SERVICE: "Human Interface Device",
    HUAWEI_SERVICE: "Huawei Link Protocol (FE86)",
    HUAWEI_VENDOR_3802_SERVICE: "Huawei vendor 0x3802",
    HUAWEI_VENDOR_E2CB_SERVICE: "Huawei vendor 0xE2CB",
    HUAWEI_VENDOR_E2E3_SERVICE: "Huawei vendor 0xE2E3",
    HUAWEI_VENDOR_CC35_SERVICE: "Huawei vendor CC353442",
    HUAWEI_SDP_SERVICE: "Huawei SDP",
}

# Advertising names. The normal (proprietary) endpoint and the standard-HRS
# broadcast endpoint use different names and different random/static addresses.
NORMAL_NAME_PREFIX = "HUAWEI Band 9-"
BROADCAST_NAME_PREFIX = "HUAWEI Band HR-"


def u(short: str) -> str:
    """Expand a 16-bit UUID such as ``180d`` to its 128-bit form."""
    short = short.lower().replace("0x", "")
    return BASE_UUID.format(short=short)


def is_huawei_band9_name(name: str | None) -> bool:
    if not name:
        return False
    name = name.strip()
    return name.lower().startswith(NORMAL_NAME_PREFIX.lower())


def is_huawei_hr_broadcast_name(name: str | None) -> bool:
    if not name:
        return False
    name = name.strip()
    return name.lower().startswith(BROADCAST_NAME_PREFIX.lower())
