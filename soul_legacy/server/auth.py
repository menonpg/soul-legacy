"""
Auth layer — works in both local (passphrase) and cloud (JWT + accounts) modes.
"""
import os, json, hashlib, secrets, sqlite3
import urllib.request as _urllib_req
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

# ── Supabase REST config ──────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TABLE = "soul_legacy_accounts"


def _use_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(params: dict) -> list:
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = _urllib_req.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?{qs}",
        headers=_sb_headers()
    )
    return json.loads(_urllib_req.urlopen(req, timeout=8).read())


def _sb_post(data: dict):
    req = _urllib_req.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        data=json.dumps(data).encode(),
        headers=_sb_headers(),
        method="POST",
    )
    _urllib_req.urlopen(req, timeout=8)


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
    try:
        from ..vault import Vault
        v = Vault(vault_dir, passphrase)
        return v.verify_passphrase()
    except Exception:
        return False


# ── Cloud: account helpers ────────────────────────────────────────────────────

def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _sqlite_get(email: str, pw_hash: str) -> Optional[dict]:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS soul_legacy_accounts (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, pw_hash TEXT,
        name TEXT, vault_dir TEXT, created_at TEXT
    )""")
    row = conn.execute(
        "SELECT id,email,name,vault_dir FROM soul_legacy_accounts WHERE email=? AND pw_hash=?",
        (email, pw_hash)
    ).fetchone()
    conn.close()
    return {"id": row[0], "email": row[1], "name": row[2], "vault_dir": row[3]} if row else None


def _sqlite_insert(record: dict):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""CREATE TABLE IF NOT EXISTS soul_legacy_accounts (
        id TEXT PRIMARY KEY, email TEXT UNIQUE, pw_hash TEXT,
        name TEXT, vault_dir TEXT, created_at TEXT
    )""")
    conn.execute(
        "INSERT OR IGNORE INTO soul_legacy_accounts VALUES (?,?,?,?,?,?)",
        (record["id"], record["email"], record["pw_hash"],
         record["name"], record["vault_dir"], record["created_at"])
    )
    conn.commit()
    conn.close()


# ── Cloud: public API ─────────────────────────────────────────────────────────

def create_cloud_account(email: str, password: str, name: str = "") -> dict:
    user_id   = secrets.token_hex(8)
    vault_dir = f"/data/vaults/{user_id}"
    now       = datetime.now().isoformat()
    record    = {
        "id": user_id, "email": email,
        "pw_hash": _hash_pw(password),
        "name": name, "vault_dir": vault_dir, "created_at": now,
    }

    if _use_supabase():
        try:
            _sb_post(record)
        except Exception as e:
            err = str(e)
            if "duplicate" in err.lower() or "unique" in err.lower() or "409" in err:
                raise HTTPException(409, "Email already registered")
            raise HTTPException(500, f"Account creation failed: {e}")
    else:
        _sqlite_insert(record)

    return {"id": user_id, "email": email, "vault_dir": vault_dir, "name": name}


def verify_cloud_login(email: str, password: str) -> Optional[dict]:
    pw_hash = _hash_pw(password)
    if _use_supabase():
        try:
            rows = _sb_get({
                "email": f"eq.{email}",
                "pw_hash": f"eq.{pw_hash}",
                "select": "id,email,name,vault_dir",
                "limit": "1",
            })
            if not rows:
                return None
            r = rows[0]
            return {"id": r["id"], "email": r["email"],
                    "name": r["name"], "vault_dir": r["vault_dir"]}
        except Exception:
            return None
    else:
        return _sqlite_get(email, pw_hash)


def get_vault_for_token(token_data: dict):
    vault_dir  = token_data.get("vault_dir")
    passphrase = token_data.get("vault_pass")
    if not vault_dir or not passphrase:
        raise HTTPException(400, "No vault in session")
    try:
        from ..vault import Vault
        if not os.path.exists(vault_dir):
            os.makedirs(vault_dir, exist_ok=True)
            v = Vault(vault_dir, passphrase)
            v.init("Cloud User", "")
            vp = Path(vault_dir) / ".vp"
            vp.write_text(passphrase)
            vp.chmod(0o600)
        return Vault(vault_dir, passphrase)
    except Exception as e:
        raise HTTPException(500, f"Vault error: {e}")
