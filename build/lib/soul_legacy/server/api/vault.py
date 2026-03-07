"""Vault CRUD API endpoints"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from ..auth import verify_token, get_vault_for_token

router = APIRouter()

SECTIONS = ["assets","insurance","legal","debts","contacts",
            "beneficiaries","digital","wishes"]

class RecordIn(BaseModel):
    section: str
    data: dict
    record_id: Optional[str] = None

@router.get("/meta")
def get_meta(token=Depends(verify_token)):
    v = get_vault_for_token(token)
    return v.meta()

@router.get("/summary")
def get_summary(token=Depends(verify_token)):
    v       = get_vault_for_token(token)
    records = v.all_records()
    meta    = v.meta()
    summary = {}
    for section, items in records.items():
        summary[section] = {"count": len(items), "items": items}
    total_assets = sum(float(r.get("value_usd") or 0)
                       for r in records.get("assets", []))
    total_debts  = sum(float(r.get("balance_usd") or 0)
                       for r in records.get("debts", []))
    return {
        "meta": meta, "sections": summary,
        "totals": {"assets": total_assets, "debts": total_debts,
                   "net_worth": total_assets - total_debts}
    }

@router.get("/{section}")
def list_section(section: str, token=Depends(verify_token)):
    if section not in SECTIONS:
        raise HTTPException(400, f"Unknown section: {section}")
    v    = get_vault_for_token(token)
    ids  = v.list(section)
    return {"section": section, "records": [v.read(section, rid) for rid in ids]}

@router.post("/{section}")
def add_record(section: str, body: RecordIn, token=Depends(verify_token)):
    if section not in SECTIONS:
        raise HTTPException(400, f"Unknown section: {section}")
    v   = get_vault_for_token(token)
    rid = body.record_id or str(uuid.uuid4())[:8]
    data = {**body.data, "id": rid}
    v.write(section, rid, data)
    return {"id": rid, "section": section}

@router.put("/{section}/{record_id}")
def update_record(section: str, record_id: str, body: RecordIn,
                  token=Depends(verify_token)):
    v = get_vault_for_token(token)
    v.write(section, record_id, {**body.data, "id": record_id})
    return {"id": record_id, "section": section}

@router.delete("/{section}/{record_id}")
def delete_record(section: str, record_id: str, token=Depends(verify_token)):
    v = get_vault_for_token(token)
    v.delete(section, record_id)
    return {"deleted": True}
