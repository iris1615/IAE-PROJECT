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

_STRATEGY_CUES = {
    "timeline": {
        "time",
        "timeline",
        "timestamp",
        "at",
        "when",
        "before",
        "after",
        "around",
    },
    "credibility": {
        "witness",
        "testimony",
        "statement",
        "unreliable",
        "credible",
        "consistency",
        "inconsistent",
        "recollection",
        "alibi",
    },
    "forensic": {
        "forensic",
        "physical",
        "evidence",
        "trace",
        "scene",
        "photo",
        "image",
        "footage",
        "timestamp",
        "camera",
    },
    "logic": {
        "because",
        "therefore",
        "thus",
        "so",
        "implies",
        "suggests",
        "if",
        "then",
    },
    "court-record": {
        "court",
        "record",
        "material",
        "admissible",
        "admissibility",
        "credibility",
        "contradiction",
        "official",
    },
}


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9:']+", text.lower())
        if len(token) >= 4 and token not in _STOPWORDS
    }


def _has_time_like_token(text: str) -> bool:
    return bool(re.search(r"\b\d{1,2}:\d{2}\b", text))


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


def _resolve_testimony(bundle: Dict, statement_id: str) -> Optional[Dict]:
    testimonies = bundle.get("testimonies", {})
    if isinstance(testimonies, list):
        for testimony in testimonies:
            if not isinstance(testimony, dict):
                continue
            for statement in testimony.get("statements", []):
                if statement.get("id") == statement_id:
                    return testimony
        return None

    if isinstance(testimonies, dict):
        if testimonies.get("statements"):
            for statement in testimonies.get("statements", []):
                if statement.get("id") == statement_id:
                    return testimonies

        for testimony in testimonies.values():
            if not isinstance(testimony, dict):
                continue
            for statement in testimony.get("statements", []):
                if statement.get("id") == statement_id:
                    return testimony

    return None


def _evidence_items(bundle: Dict) -> list[Dict]:
    evidence = bundle.get("evidence", {})
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if isinstance(evidence, dict) and evidence.get("id"):
        return [evidence]
    return []


def verify_candidate(
    bundle: Dict,
    candidate: CandidateArgument,
    retrieved: Iterable[RetrievedChunk] | None = None,
    current_statement_id: Optional[str] = None  # <-- NOVO: Forçado pelo loop do jogo
) -> VerifierResult:
    
    #gets id of the statement
    stmt_id = getattr(candidate, "target_statement_id", None) or current_statement_id
    if not stmt_id:
        return VerifierResult(False, "Missing target_statement_id")

    testimony = _resolve_testimony(bundle, stmt_id)
    if testimony is None:
        return VerifierResult(False, f"Unknown statement '{stmt_id}'")

    stmts = {stmt.get("id"): stmt for stmt in testimony.get("statements", [])}
    if stmt_id not in stmts:
        return VerifierResult(False, f"Unknown statement '{stmt_id}'")
    stmt = stmts[stmt_id]

    # validations of evidence
    evidence_id = getattr(candidate, "evidence_id", None)
    evidence_text = ""
    
    if evidence_id:  # only validates proof if the candidate has it
        evidence_items = _evidence_items(bundle)
        evidence = next((item for item in evidence_items if item.get("id") == evidence_id), None)
        if evidence is None:
            return VerifierResult(False, f"Unknown evidence_id '{evidence_id}'")

        expected = stmt.get("contradicted_by")
        if expected and expected != evidence_id:
            return VerifierResult(
                False,
                f"Contradiction mismatch: expected '{expected}', got '{evidence_id}'",
            )
            
        evidence_chunks = list(retrieved or [])
        evidence_chunk = _find_retrieved_chunk(evidence_chunks, evidence_id)
        if evidence_chunk is not None:
            evidence_text = evidence_chunk.content
        else:
            evidence_text = f"{evidence.get('name', '')} {evidence.get('description', '')}".strip()

    # Grounding & Text
    statement_text = stmt.get("text", "")
    truth = bundle.get("truth", {})
    truth_facts = " ".join(fact.get("truth", "") for fact in truth.get("facts", []))
    timeline_events = " ".join(f"{event.get('time', '')} {event.get('event', '')}" for event in truth.get("timeline", []))
    grounding_basis = " ".join(part for part in [evidence_text, statement_text, truth_facts, timeline_events] if part).strip()

    # if we dont have a basis to validate, we give one
    if not grounding_basis:
        grounding_basis = statement_text

    argument_text = getattr(candidate, "argument", "") or getattr(candidate, "text", "")
    grounding_score = _overlap_score(argument_text, grounding_basis)
    
    # Reduzimos ligeiramente a tolerância para 0.01 caso não haja prova injetada em texto
    if grounding_score < 0.01:
        return VerifierResult(
            False,
            f"Ungrounded argument: overlap too weak (score={grounding_score:.2f})",
        )

    # inference strategy
    cand_strategy = getattr(candidate, "strategy", "logic").lower()
    strategy_cues = _STRATEGY_CUES.get(cand_strategy)
    argument_lower = argument_text.lower()
    
    if cand_strategy == "timeline":
        has_strategy_cue = _has_time_like_token(argument_text) or any(cue in argument_lower for cue in strategy_cues or ())
    else:
        has_strategy_cue = bool(strategy_cues and any(cue in argument_lower for cue in strategy_cues))

    if strategy_cues and not has_strategy_cue:
        return VerifierResult(
            False,
            f"Ungrounded argument: strategy '{cand_strategy}' lacks matching cue",
        )

    reasoning_markers = ("because", "therefore", "so", "thus", "implies", "suggests", "which means", "if ", "should")
    if not any(marker in argument_lower for marker in reasoning_markers):
        return VerifierResult(
            False,
            "Ungrounded argument: missing an inferential step",
        )

    return VerifierResult(True, "ok")