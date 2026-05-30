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
