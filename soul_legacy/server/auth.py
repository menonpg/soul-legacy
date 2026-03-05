"""
Auth layer — works in both local (passphrase) and cloud (JWT + accounts) modes.
"""
import os, json, hashlib, secrets, sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import jwt
from fastapi import Header, HTTPException

SECRET_KEY  = os.environ.get("SECRET_KEY", secrets.token_hex(32))
ALGORITHM   = "HS256"
TOKEN_EXP_H = 24
DB_PATH     = os.environ.get("ACCOUNTS_DB",
              os.path.expanduser("~/.soul-legacy/accounts.db"))


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_token(payload: dict) -> str:
    data = {**payload, "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXP_H)}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired — please unlock again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def verify_token(authorization: str = Header(default="")):
    """FastAPI dependency — validates Bearer token"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing authorization header")
    return decode_token(authorization[7:])


# ── Local: passphrase ─────────────────────────────────────────────────────────

def verify_passphrase(vault_dir: str, passphrase: str) -> bool:
    from ..vault import Vault
    try:
        v = Vault(vault_dir, passphrase)
        return v.verify_passphrase()
    except:
        return False


# ── Cloud: account DB (SQLite locally, Postgres via env on Railway) ───────────

def _get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
        id         TEXT PRIMARY KEY,
        email      TEXT UNIQUE,
        pw_hash    TEXT,
        name       TEXT,
        vault_dir  TEXT,
        created_at TEXT
    )""")
    conn.commit()
    return conn


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_cloud_account(email: str, password: str, name: str = "") -> dict:
    db        = _get_db()
    user_id   = secrets.token_hex(8)
    vault_dir = os.path.expanduser(f"~/.soul-legacy/vaults/{user_id}")
    os.makedirs(vault_dir, exist_ok=True)

    # Init vault with a random passphrase (stored hashed, managed by server)
    vault_pass = secrets.token_hex(16)
    from ..vault import Vault
    v = Vault(vault_dir, vault_pass)
    v.init(name or email, email)

    # Store vault passphrase encrypted (simple for now — improve with KMS)
    vp_path = Path(vault_dir) / ".vp"
    vp_path.write_text(vault_pass)
    vp_path.chmod(0o600)

    db.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?)",
               (user_id, email, _hash_pw(password), name, vault_dir,
                datetime.now().isoformat()))
    db.commit()
    return {"id": user_id, "email": email, "vault_dir": vault_dir, "name": name}


def verify_cloud_login(email: str, password: str) -> Optional[dict]:
    db  = _get_db()
    row = db.execute("SELECT id,email,name,vault_dir FROM accounts WHERE email=? AND pw_hash=?",
                     (email, _hash_pw(password))).fetchone()
    if not row:
        return None
    return {"id": row[0], "email": row[1], "name": row[2], "vault_dir": row[3]}


def get_vault_for_token(token_data: dict):
    """Get an unlocked Vault from token payload"""
    from ..vault import Vault
    vault_dir = token_data.get("vault_dir", "")
    if token_data.get("mode") == "cloud":
        # Read managed passphrase
        vp = Path(vault_dir) / ".vp"
        if not vp.exists():
            raise HTTPException(500, "Vault passphrase not found")
        passphrase = vp.read_text().strip()
    else:
        # Local mode — passphrase embedded in token
        passphrase = token_data.get("passphrase", "")
        if not passphrase:
            raise HTTPException(401, "No passphrase in token")
    return Vault(vault_dir, passphrase)
