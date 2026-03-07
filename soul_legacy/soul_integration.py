"""
soul-legacy ← soul.py v2.0 integration

Uses soul.py HybridAgent for:
  RAG    — fast retrieval for focused questions
           "What's the policy number for my life insurance?"
  RLM    — recursive synthesis for exhaustive questions  
           "Summarize everything I need to settle this estate"
  Router — auto-selects RAG vs RLM per query
  Darwin — evolving persona based on interactions (optional)

The vault's structured records + ingested documents are formatted as MEMORY.md
and passed to HybridAgent, which handles all routing and retrieval.
"""
import os, sys, json, time, tempfile
from pathlib import Path
from typing import Optional
from .vault import Vault
from .chat import build_memory_md, DEFAULT_SOUL


def _ensure_soul_path():
    """Add soul.py to Python path if available."""
    soul_path = os.environ.get("SOUL_PATH", os.path.expanduser("~/Documents/soul.py"))
    if os.path.isdir(soul_path) and soul_path not in sys.path:
        sys.path.insert(0, soul_path)


class SoulLegacyAgent:
    """
    Full soul.py v2.0 agent for the estate vault.
    
    Wraps HybridAgent with vault-specific context loading.
    Features: RAG + RLM + Auto-Router + Memory
    
    Usage:
        agent = SoulLegacyAgent(vault, api_key="sk-ant-...")
        result = agent.ask("What life insurance do I have?")
        result = agent.ask("Summarize everything for my executor")
    """

    def __init__(self, vault: Vault, api_key: str = None,
                 model: str = "claude-sonnet-4-20250514",
                 provider: str = "anthropic",
                 mode: str = "auto",  # auto | rag | rlm
                 evolve: bool = False):
        """
        Args:
            vault: Initialized Vault instance
            api_key: LLM API key (defaults to env var)
            model: Chat model to use
            provider: anthropic | gemini | openai
            mode: auto (recommended) | rag (forced RAG) | rlm (forced RLM)
            evolve: Enable Darwin persona evolution (experimental)
        """
        self.vault = vault
        self.model = model
        self.provider = provider
        self.mode = mode
        self.evolve = evolve
        self._interactions = []
        
        # Resolve API key
        self.api_key = api_key
        if not self.api_key:
            env_keys = {
                "anthropic": "ANTHROPIC_API_KEY",
                "gemini": "GEMINI_API_KEY",
                "openai": "OPENAI_API_KEY",
            }
            self.api_key = os.environ.get(env_keys.get(provider, "ANTHROPIC_API_KEY"), "")
        
        if not self.api_key:
            raise ValueError(f"API key not set for provider {provider}")
        
        # Set up paths
        _ensure_soul_path()
        self._tmpdir = tempfile.mkdtemp()
        
        # Load or initialize soul
        self._soul_path = Path(vault.dir) / "SOUL.md"
        if not self._soul_path.exists():
            meta = vault.meta()
            owner = meta.get("owner_name", "the estate owner")
            self._soul_path.write_text(DEFAULT_SOUL.replace("the estate owner", owner))
        
        # Agent will be created per-query with fresh memory context
        self._agent = None

    def _get_agent(self, question: str = None):
        """Create HybridAgent with current vault context."""
        try:
            from hybrid_agent import HybridAgent
        except ImportError:
            raise ImportError(
                "soul.py HybridAgent not found. "
                "Set SOUL_PATH env var or install soul-agent>=0.2.0"
            )
        
        # Write SOUL.md to temp
        tmp_soul = os.path.join(self._tmpdir, "SOUL.md")
        with open(tmp_soul, "w") as f:
            f.write(self._soul_path.read_text())
        
        # Write MEMORY.md with vault context
        memory_content = build_memory_md(self.vault, question)
        tmp_memory = os.path.join(self._tmpdir, "MEMORY.md")
        with open(tmp_memory, "w") as f:
            f.write(memory_content)
        
        return HybridAgent(
            soul_path=tmp_soul,
            memory_path=tmp_memory,
            mode=self.mode,
            provider=self.provider,
            api_key=self.api_key,
            chat_model=self.model,
        )

    def ask(self, question: str, remember: bool = True) -> dict:
        """
        Ask the agent a question.
        
        Returns:
            answer: The response text
            route: RAG or RLM
            total_ms: Response time
            rag_context: Retrieved chunks (if RAG)
            rlm_meta: Synthesis metadata (if RLM)
        """
        t0 = time.time()
        
        # Create agent with fresh context for this question
        agent = self._get_agent(question)
        result = agent.ask(question, remember=False)
        
        total_ms = int((time.time() - t0) * 1000)
        result["total_ms"] = total_ms
        
        if remember:
            self._append_memory(question, result.get("answer", ""), result.get("route", ""))
            self._interactions.append({
                "question": question,
                "answer": result.get("answer", ""),
                "route": result.get("route", ""),
            })
            
            # Darwin: evolve soul every 10 interactions
            if self.evolve and len(self._interactions) % 10 == 0:
                self._evolve_soul()
        
        return result

    def _append_memory(self, question: str, answer: str, route: str):
        """Append interaction to vault MEMORY.md for continuity."""
        mem_path = Path(self.vault.dir) / "MEMORY.md"
        if not mem_path.exists():
            mem_path.write_text("# Estate Vault Memory\n\n")
        
        entry = (
            f"\n## {time.strftime('%Y-%m-%d %H:%M')} [{route}]\n"
            f"**Q:** {question}\n"
            f"**A:** {answer[:500]}{'...' if len(answer) > 500 else ''}\n"
        )
        with open(mem_path, "a") as f:
            f.write(entry)

    def _evolve_soul(self):
        """Darwin step: evolve the advisor persona based on interactions."""
        if len(self._interactions) < 3:
            return
        
        try:
            from hybrid_agent import AnthropicREST
            client = AnthropicREST(self.api_key)
        except:
            return
        
        recent = self._interactions[-10:]
        history = "\n".join(
            f"Q: {i['question']}\nA: {i['answer'][:200]}..."
            for i in recent
        )
        
        current_soul = self._soul_path.read_text()
        
        evolved = client.messages_create(
            model="claude-haiku-4-5",
            max_tokens=400,
            messages=[{"role": "user", "content":
                f"Improve this AI estate advisor's persona based on recent interactions.\n\n"
                f"Current:\n{current_soul}\n\n"
                f"Recent Q&A:\n{history}\n\n"
                f"Refine for this family's needs. Keep under 200 words. Return only the improved text."
            }]
        )
        
        self._soul_path.write_text(evolved)

    def remember(self, note: str):
        """Manually add a note to vault memory."""
        self._append_memory("[manual note]", note, "MANUAL")

    def soul(self) -> str:
        """Return current soul/persona."""
        return self._soul_path.read_text()

    def stats(self) -> dict:
        """Return interaction statistics."""
        return {
            "total_interactions": len(self._interactions),
            "routes": {
                "RAG": sum(1 for i in self._interactions if i.get("route") == "RAG"),
                "RLM": sum(1 for i in self._interactions if i.get("route") == "RLM"),
            }
        }
