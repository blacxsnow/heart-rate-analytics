"""Huawei TLV encryption helpers (AES-GCM).

On the captured Band 9 session the proprietary TLV envelope is:

    TLV 0x7C, len 1, value 0x01       encryption flag
    TLV 0x7D, len 16, value <IV>      GCM IV
    TLV 0x7E, len n, value <ct||tag>  AES-GCM ciphertext + 16-byte tag

The per-session key is obtained through HiChain3 authentication. This module
does not store or derive keys; callers must supply them from a secure store.

`cryptography` is an optional dependency (`pip install -e '.[proprietary]'`).
"""

from __future__ import annotations

from .protocol import TLV

ENC_FLAG_TAG = 0x7C
IV_TAG = 0x7D
CIPHERTEXT_TAG = 0x7E
GCM_TAG_LEN = 16


class TLVCryptoError(ValueError):
    pass


def decrypt_tlv_gcm(key: bytes, iv: bytes, ciphertext_with_tag: bytes) -> bytes:
    """Decrypt one encrypted TLV payload (ciphertext followed by GCM tag)."""
    if len(ciphertext_with_tag) < GCM_TAG_LEN:
        raise TLVCryptoError("ciphertext is shorter than the 16-byte GCM tag")
    try:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise TLVCryptoError("cryptography is not installed") from exc

    body = ciphertext_with_tag[:-GCM_TAG_LEN]
    tag = ciphertext_with_tag[-GCM_TAG_LEN:]
    try:
        decryptor = Cipher(algorithms.AES(key), modes.GCM(iv, tag)).decryptor()
        return decryptor.update(body) + decryptor.finalize()
    except InvalidTag as exc:
        raise TLVCryptoError("GCM authentication failed (wrong key/IV or corrupt data)") from exc


def split_encrypted_tlvs(tlvs: list[TLV]) -> tuple[bytes | None, bytes | None, bytes | None]:
    """Return ``(flag, iv, ciphertext_with_tag)`` from a TLV list, if present."""
    values = {tlv.tag: tlv.value for tlv in tlvs}
    return values.get(ENC_FLAG_TAG), values.get(IV_TAG), values.get(CIPHERTEXT_TAG)


def decrypt_from_tlvs(key: bytes, tlvs: list[TLV]) -> bytes:
    """Decrypt a TLV list that carries the 0x7C/0x7D/0x7E envelope."""
    flag, iv, ciphertext = split_encrypted_tlvs(tlvs)
    if not flag or iv is None or ciphertext is None:
        raise TLVCryptoError("not an encrypted TLV envelope")
    if len(iv) != 16:
        raise TLVCryptoError(f"unexpected IV length {len(iv)}")
    return decrypt_tlv_gcm(key, iv, ciphertext)
