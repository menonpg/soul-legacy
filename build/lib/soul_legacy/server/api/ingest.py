"""Document ingest API"""
import os, tempfile
from fastapi import APIRouter, Depends, UploadFile, File, Form
from typing import Optional
from ..auth import verify_token, get_vault_for_token

router = APIRouter()

@router.post("")
async def ingest_document(
    file: UploadFile = File(...),
    section: Optional[str] = Form(None),
    record_id: Optional[str] = Form(None),
    use_azure: bool = Form(False),
    token=Depends(verify_token)
):
    from ...ingest import ingest_file
    v = get_vault_for_token(token)

    # Save upload to temp file
    suffix = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    config = {}
    if use_azure:
        import json as _j
        try:
            keys = _j.load(open(os.path.expanduser("~/.openclaw/api_keys.json")))
            az   = keys.get("azure_openai", {})
            config = {"ocr_mode": "azure", "embed_mode": "azure",
                      "azure_endpoint": az.get("endpoint"),
                      "azure_key": az.get("api_key")}
        except: pass

    try:
        result = ingest_file(v, tmp_path, section=section,
                             record_id=record_id, config=config, verbose=False)
        os.unlink(tmp_path)
        return result
    except Exception as e:
        os.unlink(tmp_path)
        return {"error": str(e)}
