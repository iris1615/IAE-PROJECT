from __future__ import annotations

from typing import Dict, List

from project.adaptation.config import AdaptationConfig
from project.common.types import CandidateArgument


def generate_candidates(
    bundle: Dict,
    adaptation: AdaptationConfig,
    k: int = 5,
) -> List[CandidateArgument]:
    testimony = bundle["testimonies"]
    evidence = bundle["evidence"]

    target_stmt = None
    for stmt in testimony.get("statements", []):
        if stmt.get("contradicted_by") == evidence.get("id"):
            target_stmt = stmt
            break

    if target_stmt is None:
        target_stmt = testimony.get("statements", [{}])[0]

    styles = [
        "timeline pressure",
        "credibility attack",
        "forensic framing",
        "logical contradiction",
        "minimal factual",
    ]
    tones = _tone_variants(adaptation.tone)

    candidates: List[CandidateArgument] = []
    for idx in range(k):
        style = styles[idx % len(styles)]
        tone = tones[idx % len(tones)]
        candidates.append(
            CandidateArgument(
                candidate_id=f"cand_{idx + 1}",
                tone=tone,
                target_statement_id=target_stmt.get("id", "stmt_1"),
                evidence_id=evidence.get("id", "unknown_evidence"),
                argument=(
                    f"[{style}] Your statement '{target_stmt.get('text', '')}' conflicts with "
                    f"the evidence '{evidence.get('name', evidence.get('id', ''))}'."
                ),
            )
        )

    return candidates


def _tone_variants(base_tone: str) -> List[str]:
    base = base_tone.lower().strip()
    if base == "aggressive":
        return ["aggressive", "assertive", "sharp"]
    if base == "friendly":
        return ["friendly", "supportive", "calm"]
    if base == "informative":
        return ["informative", "analytical", "neutral"]
    return ["neutral", "assertive", "informative"]
