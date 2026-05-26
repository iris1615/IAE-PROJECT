from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

from project.common.types import EvidenceDocument, RetrievedChunk

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


@dataclass
class LocalRetriever:
    documents: List[EvidenceDocument]

    def similarity_search(self, query: str, k: int = 3) -> List[RetrievedChunk]:
        query_tokens = set(_tokens(query))
        scored = []
        for doc in self.documents:
            doc_tokens = set(_tokens(doc.content + " " + doc.id))
            overlap = len(query_tokens.intersection(doc_tokens))
            norm = max(len(doc_tokens), 1)
            score = overlap / norm
            scored.append((score, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        top = scored[:k]
        return [
            RetrievedChunk(
                id=doc.id,
                content=doc.content,
                score=score,
                metadata={"kind": doc.kind, **doc.metadata},
            )
            for score, doc in top
            if score > 0
        ]


def _tokens(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def maybe_build_chroma_retriever(documents: List[EvidenceDocument]):
    """Optional helper to keep a simple migration path to ChromaDB.

    Returns None when Chroma is unavailable or fails to initialize.
    """
    try:
        import chromadb
    except Exception:
        return None

    try:
        client = chromadb.Client()
        collection = client.get_or_create_collection("court_docs")
        collection.upsert(
            ids=[d.id for d in documents],
            documents=[d.content for d in documents],
            metadatas=[{"kind": d.kind, **d.metadata} for d in documents],
        )
    except Exception:
        return None

    class _ChromaRetriever:
        def similarity_search(self, query: str, k: int = 3):
            result = collection.query(query_texts=[query], n_results=k)
            ids = result.get("ids", [[]])[0]
            docs = result.get("documents", [[]])[0]
            metas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            chunks = []
            for i, doc_id in enumerate(ids):
                distance = distances[i] if i < len(distances) else 0.0
                score = 1.0 / (1.0 + float(distance))
                chunks.append(
                    RetrievedChunk(
                        id=doc_id,
                        content=docs[i] if i < len(docs) else "",
                        score=score,
                        metadata=metas[i] if i < len(metas) else {},
                    )
                )
            return chunks

    return _ChromaRetriever()
