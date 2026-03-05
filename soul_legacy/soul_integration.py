"""
soul-legacy ← soul.py integration

Gives the estate vault the full soul.py v2.0 feature set:

  RAG    — fast vector/BM25 retrieval for specific questions
           "What's the policy number for my life insurance?"

  RLM    — recursive synthesis for exhaustive questions
           "Summarize everything I need to settle this estate"
           "What are all my assets across every section?"

  Darwin — Darwinian agent that evolves its estate advisor persona
           based on what kinds of answers are most helpful to this family

  Router — auto-selects RAG vs RLM per query

  Memory — vault interactions appended to a MEMORY.md so the advisor
           learns over time (what this family cares about, what's been
           asked before, what gaps exist)

All pure REST — no native deps, no GPU, works on any platform.
"""

import os, json, re, time
from pathlib import Path
from typing import Optional
from .vault import Vault


# ── Minimal Anthropic REST client (pure requests) ─────────────────────────────

class _AnthropicREST:
    BASE = "https://api.anthropic.com/v1"

    def __init__(self, api_key: str):
        import requests as _r
        self._r = _r
        self.headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def messages_create(self, model, max_tokens, messages, system=None) -> str:
        payload = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system:
            payload["system"] = system
        r = self._r.post(f"{self.BASE}/messages",
                         headers=self.headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["content"][0]["text"].strip()


# ── Router ────────────────────────────────────────────────────────────────────

ROUTER_PROMPT = """Classify this estate-related query:
"{query}"

FOCUSED: Specific lookup (one fact, one document, one person, one account)
EXHAUSTIVE: Needs synthesis across the whole estate (summarize all, list every, what do I have, what should executor do, net worth, complete picture)

Reply with exactly one word: FOCUSED or EXHAUSTIVE"""


def _route(query: str, client, model: str = "claude-haiku-4-5") -> str:
    result = client.messages_create(
        model=model, max_tokens=5,
        messages=[{"role": "user", "content": ROUTER_PROMPT.format(query=query)}]
    )
    return "EXHAUSTIVE" if "EXHAUSTIVE" in result.upper() else "FOCUSED"


# ── RLM: Recursive synthesis over vault records ───────────────────────────────

def _rlm_retrieve(query: str, vault: Vault, client,
                  model: str = "claude-haiku-4-5",
                  chunk_size: int = 8) -> dict:
    """
    Recursively synthesize an answer by processing vault records in chunks.
    Best for exhaustive questions that span the whole estate.
    """
    records = vault.all_records()
    # Flatten all records into text entries
    entries = []
    for section, items in records.items():
        for item in items:
            safe = {k: v for k, v in item.items()
                    if k not in ("account_number", "ssn", "password")}
            entries.append(f"[{section.upper()}] {json.dumps(safe)}")

    if not entries:
        return {"answer": "No vault records found yet.", "relevant": 0, "total": 0}

    chunks       = [entries[i:i+chunk_size] for i in range(0, len(entries), chunk_size)]
    sub_summaries = []

    for chunk in chunks:
        chunk_text = "\n".join(chunk)
        summary = client.messages_create(
            model=model, max_tokens=400,
            messages=[{"role": "user", "content":
                f"From these estate records, extract ONLY what's relevant to:\n'{query}'\n\n"
                f"Records:\n{chunk_text}\n\n"
                f"Be concise. If nothing is relevant, reply: SKIP"
            }]
        )
        if "SKIP" not in summary.upper():
            sub_summaries.append(summary)

    if not sub_summaries:
        return {"answer": f"No estate records relevant to: '{query}'",
                "relevant": 0, "total": len(chunks)}

    combined = "\n\n===\n".join(sub_summaries)
    answer = client.messages_create(
        model=model, max_tokens=700,
        messages=[{"role": "user", "content":
            f"Based on these estate findings, answer the question: '{query}'\n\n"
            f"Findings:\n{combined}\n\n"
            f"Be direct, specific, and cite which sections the information came from."
        }]
    )

    return {"answer": answer, "relevant": len(sub_summaries), "total": len(chunks)}


# ── Darwin: Evolving estate advisor persona ───────────────────────────────────

DARWIN_SEED_SOUL = """You are a trusted estate advisor and family guide.
You have deep knowledge of this person's complete estate — assets, insurance,
legal documents, debts, beneficiaries, and final wishes.

You speak with warmth and clarity. You understand that people asking these
questions may be grieving. You give specific, actionable answers grounded in
actual documents and records. You cite your sources. You flag missing information.
You help executors, family members, and attorneys navigate the estate confidently."""


def _evolve_soul(soul_text: str, interactions: list, client,
                 model: str = "claude-haiku-4-5") -> str:
    """
    Darwin step: evolve the advisor's soul based on interaction history.
    Identifies what's working, what's missing, and refines the persona.
    """
    if len(interactions) < 3:
        return soul_text  # not enough data to evolve yet

    recent = interactions[-10:]
    history_text = "\n".join(
        f"Q: {i['question']}\nA: {i['answer'][:200]}..."
        for i in recent
    )

    evolved = client.messages_create(
        model=model, max_tokens=400,
        messages=[{"role": "user", "content":
            f"You are improving an AI estate advisor's system prompt based on recent interactions.\n\n"
            f"Current persona:\n{soul_text}\n\n"
            f"Recent Q&A:\n{history_text}\n\n"
            f"Refine the persona to be more helpful for this specific family's needs. "
            f"Keep it under 200 words. Return only the improved persona text."
        }]
    )
    return evolved


# ── Memory: append interactions to vault MEMORY.md ───────────────────────────

def _append_memory(vault: Vault, question: str, answer: str, route: str):
    mem_path = Path(vault.dir) / "MEMORY.md"
    if not mem_path.exists():
        mem_path.write_text("# Estate Vault Memory\n\n")
    entry = (
        f"\n## {time.strftime('%Y-%m-%d %H:%M')}\n"
        f"**Q [{route}]:** {question}\n"
        f"**A:** {answer[:500]}{'...' if len(answer)>500 else ''}\n"
    )
    with open(mem_path, "a") as f:
        f.write(entry)


# ── SoulLegacyAgent: full soul.py v2.0 feature set ───────────────────────────

class SoulLegacyAgent:
    """
    Full soul.py v2.0 agent for the estate vault.
    Features: RAG + RLM + Router + Darwin evolution + Memory

    Usage:
        agent = SoulLegacyAgent(vault, api_key="sk-ant-...")
        result = agent.ask("What life insurance do I have?")
        result = agent.ask("Summarize everything for my executor")
    """

    def __init__(self, vault: Vault, api_key: str = None,
                 model: str = "claude-haiku-4-5",
                 router_model: str = "claude-haiku-4-5",
                 evolve_every: int = 10):
        self.vault        = vault
        self.model        = model
        self.router_model = router_model
        self.evolve_every = evolve_every
        self._history     = []
        self._interactions = []
        self._call_count  = 0

        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self._client = _AnthropicREST(key)

        # Load or initialize soul
        self._soul_path = Path(vault.dir) / "SOUL.md"
        if not self._soul_path.exists():
            self._soul_path.write_text(DARWIN_SEED_SOUL)
        self._soul = self._soul_path.read_text().strip()

    def ask(self, question: str, remember: bool = True) -> dict:
        t0 = time.time()

        # Route: FOCUSED → RAG | EXHAUSTIVE → RLM
        route = _route(question, self._client, model=self.router_model)

        if route == "FOCUSED":
            answer, rag_ctx = self._rag_answer(question)
            meta = {"route": "RAG", "rag_context": rag_ctx[:200] if rag_ctx else None}
        else:
            rlm = _rlm_retrieve(question, self.vault, self._client, model=self.model)
            answer = rlm["answer"]
            meta = {"route": "RLM", "relevant_chunks": rlm["relevant"],
                    "total_chunks": rlm["total"]}

        total_ms = int((time.time() - t0) * 1000)

        if remember:
            _append_memory(self.vault, question, answer, meta["route"])
            self._interactions.append({"question": question, "answer": answer})
            self._call_count += 1

            # Darwin: evolve soul every N interactions
            if self._call_count % self.evolve_every == 0:
                self._soul = _evolve_soul(
                    self._soul, self._interactions, self._client, self.model)
                self._soul_path.write_text(self._soul)

        return {
            "answer":   answer,
            "total_ms": total_ms,
            **meta
        }

    def _rag_answer(self, question: str):
        """RAG: retrieve relevant vault context then answer"""
        from .chat import build_structured_context
        try:
            from .ingest import search
            chunks = search(self.vault, question, top_k=4)
            rag_ctx = "\n---\n".join(
                f"[{r['section']} / {r['metadata'].get('filename','record')}]\n{r['text']}"
                for r in chunks
            )
        except Exception:
            rag_ctx = ""

        structured = build_structured_context(self.vault)
        system = (
            f"{self._soul}\n\n"
            f"VAULT RECORDS:\n{structured}\n\n"
            f"RELEVANT DOCUMENT EXCERPTS:\n{rag_ctx or '(no documents ingested yet)'}"
        )

        self._history.append({"role": "user", "content": question})
        answer = self._client.messages_create(
            model=self.model, max_tokens=600,
            messages=self._history, system=system
        )
        self._history.append({"role": "assistant", "content": answer})
        return answer, rag_ctx

    def remember(self, note: str):
        """Manually add a note to vault memory"""
        _append_memory(self.vault, "[manual note]", note, "MANUAL")

    def soul(self) -> str:
        """Return current evolved soul/persona"""
        return self._soul

    def reset(self):
        self._history = []
