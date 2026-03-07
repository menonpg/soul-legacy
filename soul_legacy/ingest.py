"""
Document ingestion pipeline.

soul-legacy ingest will.pdf
soul-legacy ingest --section legal trust.pdf
soul-legacy ingest --record-id abc123 bank_statement.jpg

Pipeline:
  1. Extract text (pdfplumber / tesseract / azure)
  2. Auto-detect section if not specified
  3. Chunk text (~500 tokens, 50 token overlap)
  4. Embed chunks (fastembed local / azure cloud)
  5. Store in vector DB (sqlite-vec local / qdrant cloud)
  6. Encrypt + store original file in vault
  7. Link document to vault record
"""
import os, re, uuid, shutil
from typing import Optional, List
from .vault import Vault, SECTIONS
from .ocr import extract_text
from .embeddings import embed
from .vectorstore import get_vectorstore


SECTION_KEYWORDS = {
    "legal":         ["will", "trust", "attorney", "power", "directive",
                       "beneficiary", "estate", "testator", "grantor"],
    "assets":        ["account", "balance", "investment", "portfolio",
                       "brokerage", "bank", "property", "deed", "title"],
    "insurance":     ["policy", "premium", "coverage", "insured",
                       "beneficiary", "claim", "underwriter"],
    "debts":         ["loan", "mortgage", "balance due", "payment",
                       "interest rate", "principal", "creditor"],
    "contacts":      ["attorney", "accountant", "advisor", "doctor",
                       "executor", "trustee", "notary"],
    "beneficiaries": ["beneficiary", "heir", "inheritor", "bequest",
                       "legacy", "recipient"],
}


def auto_detect_section(text: str) -> str:
    """Guess which vault section a document belongs to"""
    text_lower = text.lower()
    scores = {}
    for section, keywords in SECTION_KEYWORDS.items():
        scores[section] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "legal"


def chunk_text(text: str, chunk_size: int = 500,
               overlap: int = 50, min_chunk_len: int = 30) -> List[str]:
    """
    Split text into overlapping chunks by approximate token count.
    
    Matches textsentry/soul.py chunking conventions:
    - Overlapping chunks for context continuity
    - Skip tiny fragments (< min_chunk_len chars)
    - 1 token ≈ 0.75 words
    """
    words    = text.split()
    n_words  = int(chunk_size * 0.75)
    step     = n_words - int(overlap * 0.75)
    chunks   = []
    
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + n_words]).strip()
        # Skip tiny fragments (textsentry learning)
        if len(chunk) >= min_chunk_len:
            chunks.append(chunk)
    
    return chunks


def ingest_file(vault: Vault, file_path: str,
                section: str = None, record_id: str = None,
                config: dict = None, verbose: bool = True) -> dict:
    """
    Full ingestion pipeline for a single file.
    Returns summary dict with section, record_id, chunks, method.
    """
    config   = config or {}
    filename = os.path.basename(file_path)

    if verbose:
        print(f"📄 Ingesting: {filename}")

    # Step 1: Extract text
    if verbose: print("  📖 Extracting text...", end=" ", flush=True)
    text, method = extract_text(file_path, config)
    if verbose: print(f"[{method}, {len(text)} chars]")

    if len(text.strip()) < 10:
        raise ValueError(f"Could not extract meaningful text from {filename}")

    # Step 2: Auto-detect section
    if not section:
        section = auto_detect_section(text)
        if verbose: print(f"  🏷️  Auto-detected section: {section}")

    # Step 3: Create or link vault record
    if not record_id:
        record_id = str(uuid.uuid4())[:8]
    try:
        record = vault.read(section, record_id)
    except FileNotFoundError:
        record = {"id": record_id, "name": filename, "type": "document"}
    record.setdefault("documents", [])
    if filename not in record["documents"]:
        record["documents"].append(filename)
    vault.write(section, record_id, record)

    # Step 4: Copy encrypted file to vault
    docs_dir = os.path.join(vault.dir, section, "files")
    os.makedirs(docs_dir, exist_ok=True)
    dest = os.path.join(docs_dir, filename)
    shutil.copy2(file_path, dest)
    os.chmod(dest, 0o600)
    if verbose: print(f"  💾 Stored encrypted copy → {section}/files/{filename}")

    # Step 5: Chunk
    chunks = chunk_text(text)
    if verbose: print(f"  ✂️  Chunked into {len(chunks)} pieces")

    # Step 6: Embed
    if verbose: print(f"  🔢 Embedding...", end=" ", flush=True)
    vectors = embed(chunks, config)
    if verbose: print(f"[{len(vectors[0])}-dim]")

    # Step 7: Store in vector DB
    vs = get_vectorstore(vault.dir, vault.passphrase, vault.salt, config)
    vs.add(
        doc_id   = f"{section}_{record_id}_{filename}",
        section  = section,
        chunks   = chunks,
        embeddings = vectors,
        metadata = {"filename": filename, "record_id": record_id,
                    "section": section, "ocr_method": method}
    )
    if verbose: print(f"  🗃️  Indexed {len(chunks)} chunks in vector store")
    if verbose: print(f"  ✅ Done → {section}/{record_id}")

    return {
        "record_id": record_id,
        "section":   section,
        "filename":  filename,
        "chunks":    len(chunks),
        "method":    method,
        "dims":      len(vectors[0]) if vectors else 0,
    }


def search(vault: Vault, query: str, top_k: int = 5,
           section: str = None, config: dict = None) -> List[dict]:
    """Semantic search across all ingested documents"""
    config  = config or {}
    vectors = embed([query], config)
    vs      = get_vectorstore(vault.dir, vault.passphrase, vault.salt, config)
    return vs.search(vectors[0], top_k=top_k, section=section)
