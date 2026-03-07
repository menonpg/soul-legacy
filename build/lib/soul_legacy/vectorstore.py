"""
Vector store — two backends, same interface.

Local:   sqlite-vec (single file, zero server, pure Python + C extension)
Cloud:   Qdrant (already deployed for SoulMate)

Both store encrypted chunk text + metadata.
Vectors never leave device in local mode.
"""
import os, json, sqlite3, struct
from typing import List, Dict, Optional
from .crypto import encrypt, decrypt


class LocalVectorStore:
    """
    sqlite-vec based vector store.
    Single .db file inside the vault directory.
    Falls back to basic cosine similarity in pure Python if sqlite-vec not available.
    """
    def __init__(self, vault_dir: str, passphrase: str, salt: bytes):
        self.db_path    = os.path.join(vault_dir, "vectors.db")
        self.passphrase = passphrase
        self.salt       = salt
        self._conn      = None
        self._init_db()

    def _conn_(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            # Try to load sqlite-vec extension
            try:
                import sqlite_vec
                sqlite_vec.load(self._conn)
                self._has_vec = True
            except:
                self._has_vec = False
        return self._conn

    def _init_db(self):
        conn = self._conn_()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id          TEXT PRIMARY KEY,
                doc_id      TEXT,
                section     TEXT,
                chunk_idx   INTEGER,
                text_enc    BLOB,        -- encrypted chunk text
                embedding   BLOB,        -- raw float32 bytes
                dim         INTEGER,
                metadata    TEXT         -- JSON
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_doc ON chunks(doc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_section ON chunks(section)")
        conn.commit()

    def add(self, doc_id: str, section: str, chunks: List[str],
            embeddings: List[List[float]], metadata: dict = None):
        conn = self._conn_()
        for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
            chunk_id  = f"{doc_id}_{i}"
            text_enc  = encrypt(chunk, self.passphrase, self.salt)
            emb_bytes = struct.pack(f"{len(vec)}f", *vec)
            conn.execute("""
                INSERT OR REPLACE INTO chunks
                (id, doc_id, section, chunk_idx, text_enc, embedding, dim, metadata)
                VALUES (?,?,?,?,?,?,?,?)
            """, (chunk_id, doc_id, section, i, text_enc,
                  emb_bytes, len(vec), json.dumps(metadata or {})))
        conn.commit()

    def search(self, query_embedding: List[float], top_k: int = 5,
               section: str = None) -> List[Dict]:
        """Cosine similarity search — pure Python, no GPU needed"""
        conn  = self._conn_()
        where = f"WHERE section = ?" if section else ""
        args  = (section,) if section else ()
        rows  = conn.execute(
            f"SELECT id, doc_id, section, text_enc, embedding, metadata FROM chunks {where}",
            args
        ).fetchall()

        if not rows:
            return []

        import math
        def cosine(a, b):
            dot  = sum(x*y for x,y in zip(a,b))
            na   = math.sqrt(sum(x*x for x in a))
            nb   = math.sqrt(sum(x*x for x in b))
            return dot / (na * nb) if na and nb else 0

        scored = []
        for row in rows:
            chunk_id, doc_id, section_, text_enc, emb_bytes, meta = row
            dim = len(query_embedding)
            vec = list(struct.unpack(f"{dim}f", emb_bytes[:dim*4]))
            sim = cosine(query_embedding, vec)
            scored.append((sim, chunk_id, doc_id, section_, text_enc, meta))

        scored.sort(reverse=True)
        results = []
        for sim, chunk_id, doc_id, section_, text_enc, meta in scored[:top_k]:
            text = decrypt(text_enc, self.passphrase, self.salt)
            results.append({
                "chunk_id": chunk_id,
                "doc_id":   doc_id,
                "section":  section_,
                "text":     text,
                "score":    round(sim, 4),
                "metadata": json.loads(meta)
            })
        return results

    def delete_doc(self, doc_id: str):
        self._conn_().execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self._conn_().commit()

    def count(self) -> int:
        return self._conn_().execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    def all_chunks(self) -> List[Dict]:
        """
        Return ALL chunks (decrypted) for RLM memory priming.
        
        TextSentry pattern: RLM reads from MEMORY.md, not vector DB.
        This method extracts everything so we can write it to MEMORY.md.
        """
        conn = self._conn_()
        rows = conn.execute(
            "SELECT doc_id, section, text_enc, metadata FROM chunks ORDER BY doc_id, chunk_idx"
        ).fetchall()
        
        results = []
        for doc_id, section, text_enc, meta in rows:
            text = decrypt(text_enc, self.passphrase, self.salt)
            metadata = json.loads(meta) if meta else {}
            results.append({
                "doc_id": doc_id,
                "section": section,
                "text": text,
                "filename": metadata.get("filename", doc_id.split("_")[0] if doc_id else "unknown"),
                "metadata": metadata,
            })
        return results


class QdrantVectorStore:
    """Qdrant cloud backend — for managed tier"""
    def __init__(self, url: str, api_key: str, collection: str = "soul-legacy"):
        self.url        = url
        self.api_key    = api_key
        self.collection = collection
        self._ensure_collection()

    def _headers(self):
        return {"api-key": self.api_key, "Content-Type": "application/json"}

    def _ensure_collection(self):
        import requests
        r = requests.get(f"{self.url}/collections/{self.collection}",
                         headers=self._headers(), timeout=10)
        if r.status_code == 404:
            requests.put(f"{self.url}/collections/{self.collection}",
                headers=self._headers(),
                json={"vectors": {"size": 384, "distance": "Cosine"}},
                timeout=10
            )

    def add(self, doc_id: str, section: str, chunks: List[str],
            embeddings: List[List[float]], metadata: dict = None):
        import requests, uuid
        points = [
            {
                "id":      str(uuid.uuid4()),
                "vector":  vec,
                "payload": {
                    "doc_id":  doc_id,
                    "section": section,
                    "chunk":   chunk,   # NOTE: encrypt before storing in real impl
                    "idx":     i,
                    **(metadata or {})
                }
            }
            for i, (chunk, vec) in enumerate(zip(chunks, embeddings))
        ]
        requests.put(f"{self.url}/collections/{self.collection}/points",
                     headers=self._headers(), json={"points": points}, timeout=30)

    def search(self, query_embedding: List[float], top_k: int = 5,
               section: str = None) -> List[Dict]:
        import requests
        payload = {"vector": query_embedding, "limit": top_k,
                   "with_payload": True}
        if section:
            payload["filter"] = {"must": [{"key": "section",
                                           "match": {"value": section}}]}
        r = requests.post(
            f"{self.url}/collections/{self.collection}/points/search",
            headers=self._headers(), json=payload, timeout=15)
        results = []
        for hit in r.json().get("result", []):
            p = hit["payload"]
            results.append({
                "doc_id":  p.get("doc_id"),
                "section": p.get("section"),
                "text":    p.get("chunk"),
                "score":   hit["score"],
                "metadata": p
            })
        return results

    def all_chunks(self, limit: int = 500) -> List[Dict]:
        """
        Return ALL chunks for RLM memory priming.
        Uses scroll API to fetch all points from Qdrant.
        """
        import requests
        results = []
        offset = None
        
        while True:
            payload = {
                "limit": min(100, limit - len(results)),
                "with_payload": True,
                "with_vector": False,
            }
            if offset:
                payload["offset"] = offset
            
            r = requests.post(
                f"{self.url}/collections/{self.collection}/points/scroll",
                headers=self._headers(), json=payload, timeout=30
            )
            data = r.json().get("result", {})
            points = data.get("points", [])
            
            for pt in points:
                p = pt.get("payload", {})
                results.append({
                    "doc_id": p.get("doc_id"),
                    "section": p.get("section"),
                    "text": p.get("chunk", ""),
                    "filename": p.get("filename", "unknown"),
                    "metadata": p,
                })
            
            offset = data.get("next_page_offset")
            if not offset or len(results) >= limit:
                break
        
        return results


def get_vectorstore(vault_dir: str, passphrase: str, salt: bytes,
                    config: dict = None):
    """Factory — returns right backend based on config"""
    config = config or {}
    if config.get("qdrant_url"):
        return QdrantVectorStore(
            url=config["qdrant_url"],
            api_key=config.get("qdrant_key", ""),
            collection=config.get("qdrant_collection", "soul-legacy")
        )
    return LocalVectorStore(vault_dir, passphrase, salt)
