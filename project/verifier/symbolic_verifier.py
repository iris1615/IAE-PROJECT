from __future__ import annotations

import re
from typing import Dict, Iterable, Optional

from project.common.types import CandidateArgument, RetrievedChunk, VerifierResult


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
    "you",
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9:']+", text.lower())
        if len(token) >= 4 and token not in _STOPWORDS
    }


def _overlap_score(argument: str, evidence_text: str) -> float:
    argument_tokens = _tokens(argument)
    evidence_tokens = _tokens(evidence_text)
    if not argument_tokens or not evidence_tokens:
        return 0.0
    shared = argument_tokens & evidence_tokens
    return len(shared) / max(1, min(len(argument_tokens), len(evidence_tokens)))


def _find_retrieved_chunk(retrieved: Iterable[RetrievedChunk], chunk_id: str) -> Optional[RetrievedChunk]:
    for chunk in retrieved:
        if chunk.id == chunk_id:
            return chunk
    return None


def verify_candidate(
    bundle: Dict,
    candidate: CandidateArgument,
    retrieved: Iterable[RetrievedChunk] | None = None,
) -> VerifierResult:
    evidence = bundle["evidence"]
    testimony = bundle["testimonies"]

    known_evidence_id = evidence.get("id")
    if candidate.evidence_id != known_evidence_id:
        return VerifierResult(False, f"Unknown evidence_id '{candidate.evidence_id}'")

    stmts = {stmt.get("id"): stmt for stmt in testimony.get("statements", [])}
    if candidate.target_statement_id not in stmts:
        return VerifierResult(False, f"Unknown statement '{candidate.target_statement_id}'")

    stmt = stmts[candidate.target_statement_id]
    expected = stmt.get("contradicted_by")
    if expected and expected != candidate.evidence_id:
        return VerifierResult(
            False,
            f"Contradiction mismatch: expected '{expected}', got '{candidate.evidence_id}'",
        )

    evidence_chunks = list(retrieved or [])
    evidence_chunk = _find_retrieved_chunk(evidence_chunks, candidate.evidence_id)
    evidence_text = ""
    if evidence_chunk is not None:
        evidence_text = evidence_chunk.content
    else:
        evidence_text = f"{evidence.get('name', '')} {evidence.get('description', '')}".strip()

    statement_text = stmt.get("text", "")
    grounding_basis = " ".join(part for part in [evidence_text, statement_text] if part).strip()

    grounding_score = _overlap_score(candidate.argument, grounding_basis)
    if grounding_score < 0.08:
        return VerifierResult(
            False,
            f"Ungrounded argument: overlap with retrieved evidence/statement is too weak (score={grounding_score:.2f})",
        )

    reasoning_markers = (
        "because",
        "therefore",
        "so",
        "thus",
        "implies",
        "suggests",
        "which means",
        "if ",
        "should",
    )
    if not any(marker in candidate.argument.lower() for marker in reasoning_markers):
        return VerifierResult(
            False,
            "Ungrounded argument: missing an inferential step",
        )

    return VerifierResult(True, "ok")
