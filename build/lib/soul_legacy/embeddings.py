"""
Embedding layer — no GPU, no PyTorch required.

Local:   fastembed (ONNX runtime, ~50MB, CPU only, ARM-compatible)
Cloud:   Azure OpenAI text-embedding (API call, zero local footprint)

Auto-selects based on config:
  SOUL_LEGACY_EMBED=local   → fastembed
  SOUL_LEGACY_EMBED=azure   → Azure OpenAI
  SOUL_LEGACY_EMBED=openai  → OpenAI API
"""
import os
from typing import List


EMBED_MODE = os.getenv("SOUL_LEGACY_EMBED", "local")


def embed(texts: List[str], config: dict = None) -> List[List[float]]:
    """Embed a list of texts. Returns list of float vectors."""
    config = config or {}
    mode   = config.get("embed_mode", EMBED_MODE)

    if mode == "azure":
        return _embed_azure(texts, config)
    elif mode == "openai":
        return _embed_openai(texts, config)
    else:
        return _embed_local(texts)


def _embed_local(texts: List[str]) -> List[List[float]]:
    """fastembed — ONNX, no PyTorch, CPU only, ARM-safe"""
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("BAAI/bge-small-en-v1.5")  # 33MB, 384-dim, fast
        return [list(vec) for vec in model.embed(texts)]
    except ImportError:
        raise ImportError(
            "fastembed not installed. Run: pip install fastembed\n"
            "Or set SOUL_LEGACY_EMBED=azure to use Azure OpenAI instead."
        )


def _embed_azure(texts: List[str], config: dict) -> List[List[float]]:
    """Azure OpenAI embeddings — zero local model footprint"""
    import requests
    endpoint   = config.get("azure_endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT", "")
    api_key    = config.get("azure_key")      or os.getenv("AZURE_OPENAI_KEY", "")
    deployment = config.get("azure_embed_deployment", "text-embedding-ada-002")
    api_ver    = "2024-02-01"

    url  = f"{endpoint}/openai/deployments/{deployment}/embeddings?api-version={api_ver}"
    resp = requests.post(url,
        headers={"Content-Type": "application/json", "api-key": api_key},
        json={"input": texts},
        timeout=30
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def _embed_openai(texts: List[str], config: dict) -> List[List[float]]:
    """OpenAI embeddings"""
    import requests
    api_key = config.get("openai_key") or os.getenv("OPENAI_API_KEY", "")
    resp = requests.post("https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": texts, "model": "text-embedding-3-small"},
        timeout=30
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]
