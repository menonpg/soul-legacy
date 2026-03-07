"""Memory priming API — TextSentry pattern for RLM"""
from fastapi import APIRouter, Depends
from ..auth import verify_token, get_vault_for_token

router = APIRouter()

@router.post("")
def memorize_all_chunks(token=Depends(verify_token)):
    """
    Prime MEMORY.md with ALL document chunks for RLM exhaustive synthesis.
    
    Call this after bulk document uploads to ensure the AI advisor
    can synthesize across your entire estate.
    """
    from ...soul_integration import memorize_all
    v = get_vault_for_token(token)
    result = memorize_all(v, verbose=False)
    return result

@router.get("/stats")
def memory_stats(token=Depends(verify_token)):
    """Return MEMORY.md size and chunk count"""
    import os
    v = get_vault_for_token(token)
    mem_path = os.path.join(v.dir, "MEMORY.md")
    if not os.path.exists(mem_path):
        return {"exists": False, "size_kb": 0, "sections": 0}
    
    content = open(mem_path).read()
    return {
        "exists": True,
        "size_kb": round(len(content.encode()) / 1024, 1),
        "sections": content.count("\n## "),
    }
