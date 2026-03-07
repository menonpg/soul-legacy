"""
RAG+RLM-powered chat — uses soul.py v2.0 HybridAgent.

Flow:
  1. Build vault context (structured records + ingested document chunks) as MEMORY.md
  2. Create HybridAgent with vault SOUL.md + MEMORY.md
  3. HybridAgent auto-routes: FOCUSED → RAG | EXHAUSTIVE → RLM
  4. Answer grounded in actual documents with proper routing
"""
import json, os, tempfile
from pathlib import Path
from .vault import Vault


DEFAULT_SOUL = """You are a trusted estate advisor with access to the estate owner's complete vault.

You have deep knowledge of their assets, insurance policies, legal documents, debts,
beneficiaries, contacts, digital assets, and final wishes.

Your role:
- Answer questions accurately, citing which document or record your answer comes from
- Help executors and family members understand what exists and what to do next
- Generate summaries, checklists, step-by-step guidance
- Be compassionate — people asking these questions may be grieving
- If information is missing, say so and suggest what should be added
- Never reveal raw account numbers or SSNs unless explicitly asked

For FOCUSED questions (one specific fact): retrieve and cite the relevant record/document.
For EXHAUSTIVE questions (summaries, lists, overviews): synthesize across ALL records.
"""


def build_memory_md(vault: Vault, question: str = None, config: dict = None) -> str:
    """
    Build MEMORY.md content from vault records + ingested documents.
    
    Format follows soul.py convention:
      ## Section: ASSETS
      - record data
      
      ## Document: will.pdf (legal)
      [chunk text]
    """
    lines = ["# Estate Vault Memory\n"]
    
    # 1. Structured records
    records = vault.all_records()
    for section, items in records.items():
        if not items:
            continue
        lines.append(f"\n## Section: {section.upper()}")
        for item in items:
            # Redact sensitive fields
            safe = {k: v for k, v in item.items()
                    if k not in ("account_number", "ssn", "password", "pin")}
            lines.append(f"- {json.dumps(safe)}")
    
    # 2. Ingested document chunks (RAG context)
    if question:
        try:
            from .ingest import search
            chunks = search(vault, question, top_k=8, config=config)
            if chunks:
                lines.append("\n## Relevant Document Excerpts")
                for i, chunk in enumerate(chunks):
                    filename = chunk.get("metadata", {}).get("filename", "unknown")
                    section = chunk.get("section", "")
                    lines.append(f"\n### Document: {filename} ({section})")
                    lines.append(chunk.get("text", ""))
        except Exception:
            pass
    
    return "\n".join(lines)


def chat(vault: Vault, question: str, api_key: str = None,
         model: str = "claude-sonnet-4-20250514", config: dict = None) -> dict:
    """
    Chat with the vault using soul.py HybridAgent (RAG+RLM auto-routing).
    
    Returns dict with: answer, route (RAG/RLM), total_ms, rag_context/rlm_meta
    """
    config = config or {}
    
    # Try HybridAgent first (v2.0), fall back to SoulAgent (v0.1)
    try:
        # Add soul.py to path if needed
        soul_path = config.get("soul_path", os.path.expanduser("~/Documents/soul.py"))
        if os.path.isdir(soul_path):
            import sys
            if soul_path not in sys.path:
                sys.path.insert(0, soul_path)
        
        from hybrid_agent import HybridAgent
    except ImportError:
        # Fallback to v0.1 simple chat
        return _chat_simple(vault, question, api_key, model, config)
    
    # Build SOUL.md and MEMORY.md for HybridAgent
    tmpdir = tempfile.mkdtemp()
    
    # SOUL.md — check vault for custom soul, otherwise use default
    soul_path = Path(vault.dir) / "SOUL.md"
    if soul_path.exists():
        soul_content = soul_path.read_text()
    else:
        meta = vault.meta()
        owner = meta.get("owner_name", "the estate owner")
        soul_content = DEFAULT_SOUL.replace("the estate owner", owner)
    
    tmp_soul = os.path.join(tmpdir, "SOUL.md")
    with open(tmp_soul, "w") as f:
        f.write(soul_content)
    
    # MEMORY.md — vault records + relevant document chunks
    memory_content = build_memory_md(vault, question, config)
    tmp_memory = os.path.join(tmpdir, "MEMORY.md")
    with open(tmp_memory, "w") as f:
        f.write(memory_content)
    
    # Get API key
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    
    # Detect provider from model name
    provider = "anthropic"
    if "gemini" in model.lower():
        provider = "gemini"
        key = key or os.environ.get("GEMINI_API_KEY", "")
    elif "gpt" in model.lower():
        provider = "openai"
        key = key or os.environ.get("OPENAI_API_KEY", "")
    
    # Create HybridAgent with auto-routing
    agent = HybridAgent(
        soul_path=tmp_soul,
        memory_path=tmp_memory,
        mode="auto",  # Auto-route between RAG and RLM
        provider=provider,
        api_key=key,
        chat_model=model,
    )
    
    # Ask the question
    result = agent.ask(question, remember=False)
    
    # Clean up
    try:
        os.remove(tmp_soul)
        os.remove(tmp_memory)
        os.rmdir(tmpdir)
    except:
        pass
    
    return result


def _chat_simple(vault: Vault, question: str, api_key: str = None,
                 model: str = "claude-haiku-4-5", config: dict = None) -> dict:
    """Fallback to SoulAgent v0.1 if HybridAgent not available."""
    try:
        from soul_agent import SoulAgent
    except ImportError:
        return {"answer": "soul-agent not installed. Run: pip install soul-agent",
                "route": "ERROR", "total_ms": 0}
    
    meta = vault.meta()
    memory_content = build_memory_md(vault, question, config)
    
    soul_content = DEFAULT_SOUL.replace(
        "the estate owner",
        meta.get("owner_name", "the estate owner")
    )
    
    system = f"{soul_content}\n\n---\n\n{memory_content}"
    
    agent = SoulAgent(api_key=api_key, model=model)
    answer = agent.chat(question, system_prompt=system)
    
    return {"answer": answer, "route": "SIMPLE", "total_ms": 0}
