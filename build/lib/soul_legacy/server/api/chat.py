"""Chat API — RAG + RLM + Darwin"""
import os
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from ..auth import verify_token, get_vault_for_token

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    mode: str = "auto"        # auto | rag | rlm
    model: str = "claude-haiku-4-5"
    api_key: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    route: str
    total_ms: int

@router.post("")
def chat(body: ChatRequest, token=Depends(verify_token)):
    from ...soul_integration import SoulLegacyAgent
    v      = get_vault_for_token(token)
    apikey = body.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    agent  = SoulLegacyAgent(v, api_key=apikey, model=body.model)
    result = agent.ask(body.message)
    return ChatResponse(
        answer   = result["answer"],
        route    = result.get("route", "?"),
        total_ms = result.get("total_ms", 0)
    )

@router.get("/soul")
def get_soul(token=Depends(verify_token)):
    """Return current evolved advisor persona"""
    import os as _os
    v  = get_vault_for_token(token)
    sp = _os.path.join(v.dir, "SOUL.md")
    return {"soul": open(sp).read() if _os.path.exists(sp) else ""}

@router.get("/memory")
def get_memory(token=Depends(verify_token)):
    import os as _os
    v  = get_vault_for_token(token)
    mp = _os.path.join(v.dir, "MEMORY.md")
    return {"memory": open(mp).read() if _os.path.exists(mp) else ""}
