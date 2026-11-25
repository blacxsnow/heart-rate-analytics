from __future__ import annotations

import pytest

crypto = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from fitness_band.crypto import TLVCryptoError, decrypt_tlv_gcm
from fitness_band.protocol import TLV


def _seal(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.GCM(iv)).encryptor()
    body = encryptor.update(plaintext) + encryptor.finalize()
    return body + encryptor.tag


def test_gcm_roundtrip():
    key = bytes(range(32))
    iv = bytes(range(16))
    plaintext = bytes.fromhex("010101020178")
    sealed = _seal(key, iv, plaintext)
    assert decrypt_tlv_gcm(key, iv, sealed) == plaintext


def test_gcm_rejects_wrong_key():
    key = bytes(range(32))
    iv = bytes(range(16))
    sealed = _seal(key, iv, b"hello")
    with pytest.raises(TLVCryptoError):
        decrypt_tlv_gcm(bytes(32), iv, sealed)


def test_gcm_rejects_short_ciphertext():
    with pytest.raises(TLVCryptoError):
        decrypt_tlv_gcm(bytes(16), bytes(16), b"short")


def test_encrypted_tlv_envelope_shape():
    # A synthetic envelope: flag, IV, ciphertext+tag.
    key = b"k" * 32
    iv = b"i" * 16
    sealed = _seal(key, iv, bytes.fromhex("010101"))
    tlvs = [
        TLV(0x7C, b"\x01"),
        TLV(0x7D, iv),
        TLV(0x7E, sealed),
    ]
    from fitness_band.crypto import decrypt_from_tlvs

    assert decrypt_from_tlvs(key, tlvs) == bytes.fromhex("010101")
