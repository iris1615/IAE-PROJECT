from pathlib import Path
import json
import hashlib
from typing import List
import chromadb
from project.common.types import EvidenceDocument
from project.retrieval.embeddings import EMBED_MODEL,embed_texts

CHROMA_DIR = Path("project/data/chroma")


def fingerprint_case(case_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(case_dir.glob("*.json")):
        h.update(p.read_bytes())
    return h.hexdigest()

def manifest_path(collection_name: str) -> Path:
    return CHROMA_DIR / f"{collection_name}_manifest.json"

def read_manifest(collection_name: str):
    p = manifest_path(collection_name)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def write_manifest(collection_name: str, data: dict):
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    p = manifest_path(collection_name)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")

def _client():
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))

def _normalize_metadata(raw_meta, fallback_kind: str):
    out = {}
    if isinstance(raw_meta, dict):
        for k, v in raw_meta.items():
            key = str(k)
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                out[key] = v
            else:
                # list/dict/etc -> string JSON
                out[key] = json.dumps(v, ensure_ascii=False)
    if "kind" not in out:
        out["kind"] = fallback_kind
    return out

def ensure_chroma_index(repo_root: Path, case_id: str, documents: List[EvidenceDocument], force: bool = False):
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    case_dir = repo_root / "cases" / case_id
    collection_name = f"court_docs_{case_id}"
    current_hash = fingerprint_case(case_dir)
    manifest = read_manifest(collection_name) or {}

    if force or manifest.get("source_hash") != current_hash or manifest.get("embeddings_model") != EMBED_MODEL:
        print("Reindexing Chroma collection:", collection_name)
        client = _client()
        # delete existing collection if present
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            pass
        collection = client.create_collection(name=collection_name)
        ids = [d.id for d in documents]
        docs = [d.content for d in documents]
        metadatas = [_normalize_metadata(d.metadata, d.kind) for d in documents]
        embeddings = embed_texts(docs, EMBED_MODEL)
        collection.upsert(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        write_manifest(collection_name, {"source_hash": current_hash, "embeddings_model": EMBED_MODEL})
        return True
    else:
        print("Chroma collection up-to-date:", collection_name)
        return False

def build_chroma_retriever(case_id: str):
    client = _client()
    collection_name = f"court_docs_{case_id}"
    collection = client.get_collection(name=collection_name)
    class _Retriever:
        def similarity_search(self, query: str, k: int = 3):
            result = collection.query(query_texts=[query], n_results=k)
            ids = result.get("ids", [[]])[0]
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            from project.common.types import RetrievedChunk
            chunks = []
            for i, doc_id in enumerate(ids):
                distance = distances[i] if i < len(distances) else 0.0
                score = 1.0 / (1.0 + float(distance))
                chunks.append(RetrievedChunk(id=doc_id, content=docs[i], score=score, metadata=metas[i] if i < len(metas) else {}))
            return chunks
    return _Retriever()