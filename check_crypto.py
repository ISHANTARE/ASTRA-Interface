import sys
sys.path.insert(0, ".")
import sqlite3
import crypto

# Init with same key the app uses
crypto.init_crypto("astra-mission-ctrl-2026-dev")

conn = sqlite3.connect("astra_platform.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT user_id, st_username, st_password FROM spacetrack_credentials").fetchall()
conn.close()

if not rows:
    print("No ST credentials stored yet — will be encrypted on first save.")
else:
    for r in rows:
        raw = r["st_password"]
        is_enc = crypto.is_encrypted(raw)
        snippet = raw[:60] + "..." if len(raw) > 60 else raw
        print(f"user_id      : {r['user_id']}")
        print(f"st_username  : {r['st_username']}")
        print(f"stored value : {snippet}")
        print(f"is_encrypted : {is_enc}")
        if is_enc:
            try:
                plain = crypto.decrypt(raw)
                print(f"decrypts OK  : yes (password length={len(plain)})")
            except Exception as e:
                print(f"decrypts OK  : NO — {e}")
        else:
            print("status       : LEGACY PLAINTEXT — will be re-encrypted on next use")
        print()
