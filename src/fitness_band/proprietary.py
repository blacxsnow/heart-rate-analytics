"""Offline helpers for the proprietary FE86 channel.

Scope
-----
This module implements only pieces that are documented and reproducible from
captures:

* CONFIRMED: LP frame/TLV encoding (delegated to :mod:`fitness_band.protocol`).
* CONFIRMED: the post-auth AES-GCM envelope used on this Band 9:
  TLV ``0x7C`` = encryption flag ``0x01``, ``0x7D`` = 16-byte IV,
  ``0x7E`` = ciphertext with a 16-byte GCM tag appended.
* CONFIRMED: the byte values for automatic HR/SpO2 and alert settings.

Nothing here performs I/O or claims hardware validation. The live HR data path
(``0x19/0x03``) and historical record layouts are deliberately not guessed.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .protocol import (
    CMD_ENABLE_AUTOMATIC_HR,
    CMD_ENABLE_AUTOMATIC_SPO,
    SERVICE_DEVICE_CONFIG,
    SERVICE_FITNESS_DATA,
    TLV,
    ProtocolError,
    build_frame,
    encode_tlvs,
)

# Post-auth envelope (confirmed in the 2026-11-25 capture).
TAG_ENCRYPTION_FLAG = 0x7C
TAG_GCM_IV = 0x7D
TAG_GCM_CIPHERTEXT = 0x7E
ENCRYPTION_AES_GCM = 0x01
GCM_IV_BYTES = 16
GCM_TAG_BYTES = 16

# Fitness-data commands confirmed by the settings capture.
CMD_TODAY_TOTAL = 0x03
CMD_HR_ALERT_HIGH = 0x1D
CMD_HR_ALERT_LOW = 0x22
CMD_SPO2_ALERT_LOW = 0x25

DEFAULT_HR_HIGH_BPM = 120
DEFAULT_HR_LOW_BPM = 40
DEFAULT_SPO2_LOW_PERCENT = 90


def _check_key(key: bytes) -> None:
    if len(key) not in (16, 24, 32):
        raise ValueError("AES key must be 16, 24 or 32 bytes")


def encrypt_tlv_block(
    plaintext: bytes,
    key: bytes,
    *,
    iv: bytes | None = None,
) -> list[TLV]:
    """Wrap ``plaintext`` in the confirmed 0x7C/0x7D/0x7E GCM envelope.

    The caller supplies the per-session key obtained from HiChain3. A fresh
    16-byte IV is generated unless one is given (tests use a fixed IV).
    """

    _check_key(key)
    if iv is None:
        iv = os.urandom(GCM_IV_BYTES)
    if len(iv) != GCM_IV_BYTES:
        raise ValueError(f"IV must be {GCM_IV_BYTES} bytes")

    sealed = AESGCM(key).encrypt(iv, plaintext, None)
    return [
        TLV(TAG_ENCRYPTION_FLAG, bytes([ENCRYPTION_AES_GCM])),
        TLV(TAG_GCM_IV, iv),
        TLV(TAG_GCM_CIPHERTEXT, sealed),
    ]


def decrypt_tlv_block(tlvs: Iterable[TLV], key: bytes) -> bytes:
    """Decrypt a 0x7C/0x7D/0x7E envelope and return the plaintext TLV block."""

    _check_key(key)
    values = {tlv.tag: tlv.value for tlv in tlvs}

    flag = values.get(TAG_ENCRYPTION_FLAG)
    if flag is None or flag != bytes([ENCRYPTION_AES_GCM]):
        raise ProtocolError("missing or unsupported encryption flag (0x7C)")
    iv = values.get(TAG_GCM_IV)
    if iv is None or len(iv) != GCM_IV_BYTES:
        raise ProtocolError("missing or invalid GCM IV (0x7D)")
    sealed = values.get(TAG_GCM_CIPHERTEXT)
    if sealed is None or len(sealed) < GCM_TAG_BYTES:
        raise ProtocolError("missing or truncated GCM ciphertext (0x7E)")

    try:
        return AESGCM(key).decrypt(iv, sealed, None)
    except Exception as exc:
        raise ProtocolError(f"GCM authentication failed: {exc}") from exc


def wrap_frame(
    service_id: int,
    command_id: int,
    tlvs: Iterable[TLV],
    *,
    key: bytes | None = None,
    iv: bytes | None = None,
) -> bytes:
    """Build a frame, encrypting the TLV block when ``key`` is supplied."""

    block = list(tlvs)
    if key is not None:
        block = encrypt_tlv_block(encode_tlvs(block), key, iv=iv)
    return build_frame(service_id, command_id, block)


def auto_hr_frame(enabled: bool) -> bytes:
    """0x07/0x17 automatic-heart-rate on/off (CONFIRMED bytes)."""

    return build_frame(
        SERVICE_FITNESS_DATA,
        CMD_ENABLE_AUTOMATIC_HR,
        [TLV(0x01, b"\x01" if enabled else b"\x00")],
    )


def auto_spo2_frame(enabled: bool) -> bytes:
    """0x07/0x24 automatic-SpO2 on/off (CONFIRMED bytes)."""

    return build_frame(
        SERVICE_FITNESS_DATA,
        CMD_ENABLE_AUTOMATIC_SPO,
        [TLV(0x01, b"\x01" if enabled else b"\x00")],
    )


def today_total_frame() -> bytes:
    """0x07/0x03 request today's totals (CONFIRMED bytes)."""

    return build_frame(SERVICE_FITNESS_DATA, CMD_TODAY_TOTAL, [TLV(0x01)])


def _alert_frame(command_id: int, value: int) -> bytes:
    if not 0 <= value <= 0xFF:
        raise ValueError("threshold must fit in one byte")
    return build_frame(
        SERVICE_FITNESS_DATA,
        command_id,
        [TLV(0x01, b"\x01"), TLV(0x02, bytes([value]))],
    )


def hr_alert_high_frame(bpm: int = DEFAULT_HR_HIGH_BPM) -> bytes:
    """0x07/0x1D high-HR alert threshold (CONFIRMED bytes)."""

    return _alert_frame(CMD_HR_ALERT_HIGH, bpm)


def hr_alert_low_frame(bpm: int = DEFAULT_HR_LOW_BPM) -> bytes:
    """0x07/0x22 low-HR alert threshold (CONFIRMED bytes)."""

    return _alert_frame(CMD_HR_ALERT_LOW, bpm)


def spo2_alert_frame(percent: int = DEFAULT_SPO2_LOW_PERCENT) -> bytes:
    """0x07/0x25 low-SpO2 alert threshold (CONFIRMED bytes)."""

    return _alert_frame(CMD_SPO2_ALERT_LOW, percent)


def security_negotiation_request(
    peer_auth_id: bytes,
    phone_name: str,
    *,
    auth_mode: int = 0x04,
) -> bytes:
    """Build the 0x01/0x33 security-negotiation request observed on-device.

    The captured request contained TLVs 0x01=04 (HiChain3), 0x02=01,
    0x05=<16-byte phone id>, 0x03=01, 0x04=00, 0x06="phoneIdentify",
    0x07=<phone model>. The caller supplies the phone identifier.
    """

    if len(peer_auth_id) != 16:
        raise ValueError("peer identifier must be 16 bytes")
    return build_frame(
        SERVICE_DEVICE_CONFIG,
        0x33,
        [
            TLV(0x01, bytes([auth_mode])),
            TLV(0x02, b"\x01"),
            TLV(0x05, peer_auth_id),
            TLV(0x03, b"\x01"),
            TLV(0x04, b"\x00"),
            TLV(0x06, b"phoneIdentify"),
            TLV(0x07, phone_name.encode("utf-8")),
        ],
    )
