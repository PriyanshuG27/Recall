"""
backend/services/encryption.py
================================
Single encryption/decryption utility for all sensitive data in Recall.

Used for:
  - items.raw_text         — encrypted before every DB write
  - users.google_refresh_token — encrypted before every DB write

Key rotation procedure:
  1. Generate new FERNET_KEY via `make fernet`.
  2. Read all encrypted rows using the OLD key (decrypt).
  3. Re-encrypt every value with the NEW key.
  4. Update FERNET_KEY in Render environment.
  5. Deploy — new key active from this point.
  See SECURITY.md §Key Rotation for the full runbook.

SECURITY RULES (non-negotiable):
  - FERNET_KEY comes from settings ONLY — never hardcoded or passed as param.
  - encrypt() must NEVER log its input.
  - decrypt() must NEVER log its output.
  - Every site that writes raw_text or google_refresh_token MUST call encrypt().
"""

from __future__ import annotations

import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """
    Returns a Fernet instance initialised with the key from settings.
    Imports Settings fresh each call so unit-test monkeypatching works correctly.
    """
    import importlib
    import backend.config as _cfg_module
    importlib.reload(_cfg_module)
    settings = _cfg_module.settings

    if settings is None:
        raise RuntimeError(
            "Settings failed to load — cannot initialise Fernet cipher. "
            "Ensure all required environment variables are set."
        )
    return Fernet(settings.FERNET_KEY.encode())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext string using Fernet symmetric encryption.

    Fernet uses AES-128-CBC with a random IV + HMAC-SHA256 for authenticity.
    Two calls with the same input produce DIFFERENT ciphertexts (random IV).

    Args:
        plaintext: The sensitive string to encrypt (e.g. raw OCR text).

    Returns:
        URL-safe base64-encoded ciphertext string, safe to store in TEXT columns.

    Raises:
        RuntimeError: If settings are not loaded.
        ValueError:   If plaintext is not a string.
    """
    if not isinstance(plaintext, str):
        raise ValueError("encrypt() requires a str — got %s" % type(plaintext).__name__)

    # SECURITY: do NOT log plaintext here under any circumstances
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a Fernet ciphertext back to plaintext.

    Args:
        ciphertext: The base64-encoded ciphertext produced by encrypt().

    Returns:
        The original plaintext string.

    Raises:
        InvalidToken:  If the ciphertext is tampered, corrupted, or encrypted
                       with a different key.
        RuntimeError:  If settings are not loaded.
    """
    if not isinstance(ciphertext, str):
        raise ValueError("decrypt() requires a str — got %s" % type(ciphertext).__name__)

    f = _get_fernet()
    # SECURITY: do NOT log the return value here under any circumstances
    return f.decrypt(ciphertext.encode()).decode()


def encrypt_if_not_none(value: Optional[str]) -> Optional[str]:
    """
    Convenience helper — encrypts value only when it is not None.

    Useful for optional fields like google_refresh_token that may be NULL.

    Args:
        value: Plaintext string or None.

    Returns:
        Encrypted ciphertext string, or None if value was None.
    """
    return encrypt(value) if value is not None else None


def decrypt_if_not_none(value: Optional[str]) -> Optional[str]:
    """
    Convenience helper — decrypts value only when it is not None.

    Args:
        value: Ciphertext string or None.

    Returns:
        Decrypted plaintext string, or None if value was None.
    """
    return decrypt(value) if value is not None else None
