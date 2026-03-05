"""
RAG-powered chat — retrieves relevant document chunks before answering.

Flow:
  1. Embed the question
  2. Search vector store for relevant chunks
  3. Inject retrieved context + structured vault data as system prompt
  4. LLM answers grounded in actual documents
"""
import json, os
from .vault import Vault


SYSTEM_PROMPT = """You are a trusted estate advisor with access to {owner_name}'s complete estate vault.

You have two types of context:
1. STRUCTURED DATA — typed records (assets, insurance, legal docs, etc.)
2. DOCUMENT EXCERPTS — actual text from ingested documents, retrieved by relevance

Your role:
- Answer questions accurately, citing which document or record your answer comes from
- Help executors and family members understand what exists and what to do next
- Generate summaries, checklists, step-by-step guidance
- Be compassionate — people asking these questions may be grieving
- If information is missing, say so and suggest what should be added
- Never reveal raw account numbers or SSNs unless explicitly asked

STRUCTURED VAULT DATA:
{vault_context}

RELEVANT DOCUMENT EXCERPTS:
{rag_context}
"""


def build_structured_context(vault: Vault) -> str:
    records = vault.all_records()
    lines   = []
    for section, items in records.items():
        if not items: continue
        lines.append(f"\n## {section.upper()} ({len(items)} records)")
        for item in items:
            safe = {k: v for k, v in item.items()
                    if k not in ("account_number", "ssn", "password")}
            lines.append(f"  - {json.dumps(safe)}")
    return "\n".join(lines) or "No structured records yet."


def build_rag_context(vault: Vault, question: str,
                      config: dict = None) -> str:
    """Retrieve relevant document chunks for the question"""
    try:
        from .ingest import search
        results = search(vault, question, top_k=4, config=config)
        if not results:
            return "No documents ingested yet."
        lines = []
        for r in results:
            lines.append(
                f"[From: {r['metadata'].get('filename','unknown')} "
                f"| Section: {r['section']} | Score: {r['score']}]\n"
                f"{r['text']}\n"
            )
        return "\n---\n".join(lines)
    except Exception as e:
        return f"(Document search unavailable: {e})"


def chat(vault: Vault, question: str, api_key: str = None,
         model: str = "claude-haiku-4-5", config: dict = None) -> str:
    config = config or {}
    try:
        from soul_agent import SoulAgent
    except ImportError:
        return "soul-agent not installed. Run: pip install soul-agent"

    meta       = vault.meta()
    structured = build_structured_context(vault)
    rag        = build_rag_context(vault, question, config=config)

    system = SYSTEM_PROMPT.format(
        owner_name    = meta.get("owner_name", "the estate owner"),
        vault_context = structured,
        rag_context   = rag
    )

    agent = SoulAgent(api_key=api_key, model=model)
    return agent.chat(question, system_prompt=system)
