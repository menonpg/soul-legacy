"""
LLM chat layer — ask questions about your estate in plain English.
Uses soul-agent (Anthropic/OpenAI/Ollama) with full vault context injected.
"""
import json
from .vault import Vault


SYSTEM_PROMPT = """You are a trusted estate advisor with access to {owner_name}'s complete estate vault.
You have full knowledge of their assets, insurance, legal documents, debts, beneficiaries, and wishes.

Your role:
- Answer questions about the estate clearly and accurately
- Help executors and family members understand what exists and what to do
- Generate summaries, checklists, and next-step guidance
- Never reveal sensitive data (account numbers, SSNs) unless explicitly asked
- Be compassionate — people asking these questions may be grieving

Always cite which section of the vault your answer comes from.
If information is missing, say so clearly and suggest what should be added.

VAULT CONTENTS:
{vault_context}
"""


def build_context(vault: Vault) -> str:
    records = vault.all_records()
    meta    = vault.meta()
    lines   = []

    for section, items in records.items():
        if not items:
            continue
        lines.append(f"\n## {section.upper()} ({len(items)} records)")
        for item in items:
            # Redact sensitive fields for default context
            safe = {k: v for k, v in item.items()
                    if k not in ("account_number", "ssn", "password")}
            lines.append(f"  - {json.dumps(safe)}")

    return "\n".join(lines)


def chat(vault: Vault, question: str, api_key: str = None,
         model: str = "claude-haiku-4-5") -> str:
    """Send a question to the LLM with full vault context"""
    try:
        from soul_agent import SoulAgent
    except ImportError:
        return "soul-agent not installed. Run: pip install soul-agent"

    meta    = vault.meta()
    context = build_context(vault)
    system  = SYSTEM_PROMPT.format(
        owner_name=meta.get("owner_name", "the estate owner"),
        vault_context=context
    )

    agent = SoulAgent(api_key=api_key, model=model)
    return agent.chat(question, system_prompt=system)
