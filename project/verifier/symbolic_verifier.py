from __future__ import annotations

from typing import Dict

from project.common.types import CandidateArgument, VerifierResult


def verify_candidate(bundle: Dict, candidate: CandidateArgument) -> VerifierResult:
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

    return VerifierResult(True, "ok")
