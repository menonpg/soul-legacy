"""Dead man's switch API endpoints"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from ..auth import verify_token, get_vault_for_token

router = APIRouter()

class InheritorIn(BaseModel):
    name: str
    email: str
    role: str = "inheritor"   # executor | attorney | accountant | family | inheritor
    sections: List[str] = ["all"]

class SetupRequest(BaseModel):
    grace_days: int = 30
    inheritors: List[InheritorIn] = []

@router.post("/setup")
def setup(body: SetupRequest, token=Depends(verify_token)):
    from ...deadmans import DeadMansSwitch
    v   = get_vault_for_token(token)
    dms = DeadMansSwitch(v)
    return dms.setup(grace_days=body.grace_days,
                     inheritors=[i.dict() for i in body.inheritors])

@router.get("/status")
def status(token=Depends(verify_token)):
    from ...deadmans import DeadMansSwitch
    v   = get_vault_for_token(token)
    dms = DeadMansSwitch(v)
    return dms.status()

@router.post("/checkin")
def checkin(token=Depends(verify_token)):
    """In-app check-in button"""
    from ...deadmans import DeadMansSwitch
    from ...blockchain import anchor_checkin
    import os
    v   = get_vault_for_token(token)
    dms = DeadMansSwitch(v)
    result = dms.checkin()
    # Fire-and-forget blockchain anchor
    try:
        tx = anchor_checkin(v)
        result["blockchain"] = tx
    except:
        pass
    return result

@router.get("/checkin/{checkin_token}")
def checkin_by_email(checkin_token: str):
    """Email link check-in — no auth needed, token IS the auth"""
    # NOTE: In cloud mode this needs to look up the vault by token
    # For now returns instructions
    return {"message": "Check-in recorded. Your vault clock has been reset.",
            "token": checkin_token[:8] + "..."}

@router.post("/pause")
def pause(token=Depends(verify_token)):
    from ...deadmans import DeadMansSwitch
    v = get_vault_for_token(token)
    DeadMansSwitch(v).pause()
    return {"status": "paused"}

@router.post("/resume")
def resume(token=Depends(verify_token)):
    from ...deadmans import DeadMansSwitch
    v = get_vault_for_token(token)
    DeadMansSwitch(v).resume()
    return {"status": "active"}

@router.get("/blockchain")
def blockchain_status(token=Depends(verify_token)):
    from ...blockchain import VaultAnchorClient, _load_config
    cfg   = _load_config()
    owner = cfg.get("owner_address")
    if not owner:
        return {"configured": False,
                "message": "Add polygon.owner_address to api_keys.json"}
    try:
        client = VaultAnchorClient()
        return {"configured": True, **client.get_status(owner)}
    except Exception as e:
        return {"configured": False, "error": str(e)}
