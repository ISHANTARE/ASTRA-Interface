"""
ASTRA-Interface — crypto.py
Symmetric encryption for reversible secrets (Space-Track credentials).

Why symmetric encryption and NOT hashing?
  - Hashing (bcrypt, sha256) is one-way: you can verify but never recover.
  - Space-Track credentials must be *retrieved* and sent to space-track.org,
    so they require reversible encryption (AES-128 via Fernet).

Key derivation:
  - The encryption key is derived from the application's SECRET_KEY using
    PBKDF2-HMAC-SHA256 (100 000 iterations, 32-byte output).
  - The derived key is NEVER stored in the database.
  - If SECRET_KEY changes, existing encrypted values become unreadable
    (users will be prompted to re-enter their ST credentials).

Security properties:
  - Database alone: useless (ciphertext without key)
  - SECRET_KEY alone: useless (no ciphertext)
  - Both together: credentials recoverable → only by the running server
"""
from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# ── Module-level Fernet instance (initialized lazily once) ──────────────────
_fernet: Fernet | None = None


def _build_fernet(secret_key: str | bytes) -> Fernet:
    """Derive a 256-bit Fernet key from the app secret using PBKDF2-HMAC-SHA256."""
    if isinstance(secret_key, str):
        secret_key = secret_key.encode("utf-8")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        # Fixed salt: acceptable here because the key material (SECRET_KEY)
        # is already high-entropy and not user-derived.
        salt=b"astra-platform-fernet-salt-v1",
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key))
    return Fernet(key)


def init_crypto(secret_key: str | bytes) -> None:
    """Call once at app startup with the Flask secret key."""
    global _fernet
    _fernet = _build_fernet(secret_key)


def _get_fernet() -> Fernet:
    if _fernet is None:
        # Fallback: derive from env var so unit tests don't need Flask context.
        secret = os.environ.get("ASTRA_SECRET_KEY", "astra-mission-ctrl-2026-dev")
        return _build_fernet(secret)
    return _fernet


# ── Public API ───────────────────────────────────────────────────────────────

def encrypt(plaintext: str) -> str:
    """Encrypt *plaintext* and return a URL-safe base64 token (str)."""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    """Decrypt a Fernet *token* and return the original plaintext.

    Raises:
        ValueError: If the token is invalid or was encrypted with a different key.
    """
    f = _get_fernet()
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError(
            "Failed to decrypt credential — the token may be corrupted or "
            "the SECRET_KEY has changed since it was stored."
        ) from exc


def is_encrypted(value: str) -> bool:
    """Heuristic: Fernet tokens always start with 'gAAA' after base64 encoding."""
    return value.startswith("gAAA")
