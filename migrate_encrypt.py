"""
One-shot migration: re-encrypt all legacy plaintext Space-Track passwords in the DB.
Run once: python migrate_encrypt.py
Safe to run multiple times (already-encrypted rows are skipped).
"""
import sys
sys.path.insert(0, ".")
import sqlite3
import crypto

crypto.init_crypto("astra-mission-ctrl-2026-dev")

conn = sqlite3.connect("astra_platform.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT user_id, st_username, st_password FROM spacetrack_credentials").fetchall()

migrated = 0
skipped  = 0

for r in rows:
    raw = r["st_password"]
    if crypto.is_encrypted(raw):
        print(f"  user {r['user_id']} ({r['st_username']}) — already encrypted, skipping.")
        skipped += 1
    else:
        encrypted = crypto.encrypt(raw)
        conn.execute(
            "UPDATE spacetrack_credentials SET st_password = ?, updated_at = datetime('now') WHERE user_id = ?",
            (encrypted, r["user_id"])
        )
        print(f"  user {r['user_id']} ({r['st_username']}) — migrated to Fernet ciphertext ✓")
        migrated += 1

conn.commit()
conn.close()
print(f"\nDone. {migrated} migrated, {skipped} already encrypted.")
