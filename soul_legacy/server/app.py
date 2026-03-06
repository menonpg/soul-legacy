"""
soul-legacy web server
Local:  soul-legacy serve  → localhost:8080, passphrase auth
Cloud:  soul-legacy serve --cloud → Railway, JWT + multi-tenant accounts

FastAPI + vanilla HTML/JS — no build step, runs anywhere, ARM-safe.
"""
import os, json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="soul-legacy", version="0.1.0", docs_url="/api/docs")

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")




@app.get("/api/mode")
def get_mode():
    """Tell the UI whether we're running in local or cloud mode."""
    mode = os.environ.get("SOUL_LEGACY_MODE", "local")
    return {"mode": mode}

# ── Auth ──────────────────────────────────────────────────────────────────────

from .auth import verify_token, create_token, verify_passphrase

class UnlockRequest(BaseModel):
    passphrase: str
    vault_dir: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/unlock")
def unlock(req: UnlockRequest):
    """Local mode: unlock vault with passphrase → get session token"""
    vault_dir = req.vault_dir or os.path.expanduser("~/.soul-legacy/vault")
    if not verify_passphrase(vault_dir, req.passphrase):
        raise HTTPException(401, "Invalid passphrase")
    token = create_token({"vault_dir": vault_dir, "mode": "local"})
    return {"token": token, "mode": "local"}

@app.post("/api/login")
def login(req: LoginRequest):
    """Cloud mode: email + password → JWT"""
    from .auth import verify_cloud_login
    user = verify_cloud_login(req.email, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token({"user_id": user["id"], "vault_dir": user["vault_dir"],
                          "mode": "cloud", "email": req.email})
    return {"token": token, "mode": "cloud", "name": user.get("name")}

@app.post("/api/signup")
def signup(req: LoginRequest):
    """Cloud mode: create account"""
    from .auth import create_cloud_account
    user = create_cloud_account(req.email, req.password)
    token = create_token({"user_id": user["id"], "vault_dir": user["vault_dir"],
                          "mode": "cloud", "email": req.email})
    return {"token": token, "mode": "cloud"}


# ── Vault API ─────────────────────────────────────────────────────────────────

from .api.vault import router as vault_router
from .api.chat  import router as chat_router
from .api.ingest import router as ingest_router
from .api.deadmans import router as deadmans_router

app.include_router(vault_router,  prefix="/api/vault",  tags=["vault"])
app.include_router(chat_router,   prefix="/api/chat",   tags=["chat"])
app.include_router(deadmans_router, prefix="/api/deadmans", tags=["deadmans"])
app.include_router(ingest_router, prefix="/api/ingest", tags=["ingest"])


# ── Serve SPA ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
@app.get("/{path:path}", response_class=HTMLResponse)
def serve_spa(path: str = ""):
    index = STATIC_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text())
    return HTMLResponse("<h1>soul-legacy server running</h1><p>Static files not found.</p>")
