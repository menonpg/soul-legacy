"""
Auth layer — works in both local (passphrase) and cloud (JWT + accounts) modes.
"""
import os, json, hashlib, secrets, sqlite3
try:
    import psycopg2
except ImportError:
    psycopg2 = None
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
    try:
        from ..vault import Vault
        v = Vault(vault_dir, passphrase)
        return v.verify_passphrase()
    except Exception:
        return False


# ── Cloud: account DB ────────────────────────────────────────────────────────
# Uses Postgres (Supabase) when DATABASE_URL is set, SQLite otherwise.
# Set DATABASE_URL=postgresql://... in Railway environment variables.

DATABASE_URL = os.environ.get("DATABASE_URL", "")
DATABASE_URL_DIRECT = os.environ.get("DATABASE_URL_DIRECT", "")  # fallback direct connection


def _get_db():
    """Returns (conn, db_type). Uses Postgres if DATABASE_URL+psycopg2 available, else SQLite."""
    if DATABASE_URL and psycopg2 is not None:
        try:
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=8)
        except Exception:
            if DATABASE_URL_DIRECT:
                conn = psycopg2.connect(DATABASE_URL_DIRECT, connect_timeout=8)
            else:
                raise
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS soul_legacy_accounts (
                id         TEXT PRIMARY KEY,
                email      TEXT UNIQUE NOT NULL,
                pw_hash    TEXT NOT NULL,
                name       TEXT DEFAULT \'\',
                vault_dir  TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
        return conn, "postgres"
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""CREATE TABLE IF NOT EXISTS soul_legacy_accounts (
            id         TEXT PRIMARY KEY,
            email      TEXT UNIQUE,
            pw_hash    TEXT,
            name       TEXT,
            vault_dir  TEXT,
            created_at TEXT
        )""")
        conn.commit()
        return conn, "sqlite"


def _hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_cloud_account(email: str, password: str, name: str = "") -> dict:
    conn, db_type = _get_db()
    user_id   = secrets.token_hex(8)
    vault_dir = f"/data/vaults/{user_id}"  # persistent path on Railway volume
    os.makedirs(vault_dir, exist_ok=True)

    vault_pass = secrets.token_hex(16)
    v = Vault(vault_dir, vault_pass)
    v.init(name or email, email)

    vp_path = Path(vault_dir) / ".vp"
    vp_path.write_text(vault_pass)
    vp_path.chmod(0o600)

    now = datetime.now().isoformat()
    record = {"id": user_id, "email": email, "pw_hash": _hash_pw(password),
              "name": name, "vault_dir": vault_dir, "created_at": now}

    if _use_supabase():
        try:
            _sb_post(record)
        except Exception as e:
            if "duplicate" in str(e).lower() or "unique" in str(e).lower() or "409" in str(e):
                raise HTTPException(409, "Email already registered")
            raise HTTPException(500, f"Account creation failed: {e}")
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute("INSERT OR IGNORE INTO soul_legacy_accounts VALUES (?,?,?,?,?,?)",
                         (user_id, email, _hash_pw(password), name, vault_dir, now))
            conn.commit()
        finally:
            conn.close()

    return {"id": user_id, "email": email, "vault_dir": vault_dir, "name": name}


def verify_cloud_login(email: str, password: str) -> Optional[dict]:
    if _use_supabase():
        try:
            rows = _sb_get({"email": f"eq.{email}", "pw_hash": f"eq.{_hash_pw(password)}",
                            "select": "id,email,name,vault_dir", "limit": "1"})
            if not rows:
                return None
            r = rows[0]
            return {"id": r["id"], "email": r["email"], "name": r["name"], "vault_dir": r["vault_dir"]}
        except Exception:
            return None
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT id,email,name,vault_dir FROM soul_legacy_accounts WHERE email=? AND pw_hash=?",
            (email, _hash_pw(password))
        ).fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "email": row[1], "name": row[2], "vault_dir": row[3]}


def get_vault_for_token(token_data: dict):
    """Get an unlocked Vault from token payload"""
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
