"""
ASTRA-Interface Platform — database.py
SQLite schema + CRUD helpers.

Credential storage security model:
  - Platform passwords  → bcrypt hash via werkzeug  (one-way, in users table)
  - Space-Track password → Fernet AES-128 ciphertext  (reversible, in spacetrack_credentials)
"""
from __future__ import annotations

import logging
import sqlite3

import crypto as _crypto

logger = logging.getLogger(__name__)
from pathlib import Path

DB_PATH = Path(__file__).parent / "astra_platform.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT    NOT NULL UNIQUE,
            email       TEXT    NOT NULL UNIQUE,
            password    TEXT    NOT NULL,
            created_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS spacetrack_credentials (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL UNIQUE,
            st_username TEXT    NOT NULL,
            st_password TEXT    NOT NULL,
            updated_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            action      TEXT    NOT NULL,
            detail      TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        """)


# ── Users ────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        return cur.lastrowid


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()


# ── Space-Track Credentials ───────────────────────────────────────────────────

def save_spacetrack_creds(user_id: int, st_user: str, st_pass: str) -> None:
    """Persist ST credentials — password is Fernet-encrypted before storage."""
    encrypted_pass = _crypto.encrypt(st_pass)
    with get_db() as conn:
        conn.execute("""
            INSERT INTO spacetrack_credentials (user_id, st_username, st_password, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                st_username = excluded.st_username,
                st_password = excluded.st_password,
                updated_at  = excluded.updated_at
        """, (user_id, st_user, encrypted_pass))


def get_spacetrack_creds(user_id: int) -> dict | None:
    """Return ST credentials with the password already decrypted.

    Handles legacy rows that were stored in plaintext before encryption was
    introduced — detected via ``crypto.is_encrypted()``; those rows are returned
    as-is and will be re-encrypted the next time the user saves their credentials.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM spacetrack_credentials WHERE user_id = ?", (user_id,)
        ).fetchone()

    if row is None:
        return None

    st_pass_stored = row["st_password"]
    if _crypto.is_encrypted(st_pass_stored):
        try:
            st_pass_plain = _crypto.decrypt(st_pass_stored)
        except ValueError:
            # Key changed — treat as missing so user re-enters creds.
            logger.warning("ST credential decryption failed for user %s (key rotation?)", user_id)
            return None
    else:
        # Legacy plaintext row — return as-is; will be re-encrypted on next save.
        logger.info("Legacy plaintext ST credential detected for user %s", user_id)
        st_pass_plain = st_pass_stored

    return {
        "st_username": row["st_username"],
        "st_password": st_pass_plain,
        "updated_at":  row["updated_at"],
    }


def _get_raw_st_password(user_id: int) -> str | None:
    """Return the raw stored password value (ciphertext or legacy plaintext).
    Used internally by app.py for the opportunistic re-encryption check.
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT st_password FROM spacetrack_credentials WHERE user_id = ?", (user_id,)
        ).fetchone()
    return row["st_password"] if row else None


# ── Activity Log ─────────────────────────────────────────────────────────────

def log_activity(user_id: int, action: str, detail: str = "") -> None:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, action, detail) VALUES (?, ?, ?)",
            (user_id, action, detail),
        )


def get_recent_activity(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_db() as conn:
        return conn.execute("""
            SELECT action, detail, created_at
            FROM activity_log
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (user_id, limit)).fetchall()
