"""
backend/tests/test_encryption.py
==================================
Unit tests for backend/services/encryption.py.

All tests use monkeypatched settings — zero real Fernet keys from disk.
"""

import pytest
from cryptography.fernet import InvalidToken


VALID_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGHIjklmnoPQRstuvwxyZ123456789",
    "DATABASE_URL": "postgresql://user:pass@localhost:5432/db?sslmode=require",
    "UPSTASH_REDIS_REST_URL": "https://dev-recall-redis.upstash.io",
    "UPSTASH_REDIS_REST_TOKEN": "dev_upstash_redis_token",
    "FERNET_KEY": "yF4P-W965hF17Bq_Q7g_oG5l8S631P9_9z-d8v7d8sA=",
    "JWT_SECRET": "8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b",
    "WEBSITE_URL": "http://localhost:5173",
}


@pytest.fixture(autouse=True)
def patch_env(monkeypatch):
    for k, v in VALID_ENV.items():
        monkeypatch.setenv(k, v)


def test_encrypt_decrypt_roundtrip():
    """decrypt(encrypt(x)) must equal x."""
    from backend.services.encryption import encrypt, decrypt

    plaintext = "Hello, Recall!"
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext


def test_encrypt_produces_different_ciphertexts():
    """Fernet uses a random IV — same plaintext must produce different ciphertexts."""
    from backend.services.encryption import encrypt

    ct1 = encrypt("hello")
    ct2 = encrypt("hello")
    assert ct1 != ct2, "Two encryptions of the same plaintext must differ (random IV)"


def test_encrypt_output_is_string():
    """encrypt() must return a str, not bytes."""
    from backend.services.encryption import encrypt

    result = encrypt("test data")
    assert isinstance(result, str)


def test_decrypt_output_is_string():
    """decrypt() must return a str, not bytes."""
    from backend.services.encryption import encrypt, decrypt

    result = decrypt(encrypt("test data"))
    assert isinstance(result, str)


def test_decrypt_tampered_ciphertext_raises():
    """Tampered ciphertext must raise InvalidToken — not silently return garbage."""
    from backend.services.encryption import decrypt

    with pytest.raises(InvalidToken):
        decrypt("this-is-not-valid-fernet-ciphertext==")


def test_encrypt_if_not_none_with_value():
    """encrypt_if_not_none should encrypt when given a string."""
    from backend.services.encryption import encrypt_if_not_none, decrypt

    result = encrypt_if_not_none("secret")
    assert result is not None
    assert decrypt(result) == "secret"


def test_encrypt_if_not_none_with_none():
    """encrypt_if_not_none should return None when given None."""
    from backend.services.encryption import encrypt_if_not_none

    assert encrypt_if_not_none(None) is None


def test_decrypt_if_not_none_with_none():
    """decrypt_if_not_none should return None when given None."""
    from backend.services.encryption import decrypt_if_not_none

    assert decrypt_if_not_none(None) is None


def test_encrypt_non_string_raises():
    """encrypt() should raise ValueError for non-string input."""
    from backend.services.encryption import encrypt

    with pytest.raises((ValueError, TypeError)):
        encrypt(12345)  # type: ignore[arg-type]


def test_no_key_in_logs(caplog, monkeypatch):
    """FERNET_KEY must NEVER appear in any log output during encryption."""
    import logging
    from backend.services.encryption import encrypt, decrypt

    fernet_key = VALID_ENV["FERNET_KEY"]

    with caplog.at_level(logging.DEBUG):
        ct = encrypt("sensitive data")
        decrypt(ct)

    for record in caplog.records:
        assert fernet_key not in record.getMessage(), (
            "FERNET_KEY appeared in log output — security violation!"
        )
