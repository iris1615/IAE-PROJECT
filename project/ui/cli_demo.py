from typing import List, Tuple

from project.common.types import CandidateArgument, VerifierResult


def print_candidates(results: List[Tuple[CandidateArgument, VerifierResult]]) -> None:
    print("\n=== Verified Candidates ===")
    for candidate, verdict in results:
        status = "OK" if verdict.valid else "REJECT"
        print(
            f"- {candidate.candidate_id} [{status}] tone={candidate.tone} "
            f"stmt={candidate.target_statement_id} evidence={candidate.evidence_id}"
        )
        print(f"  {candidate.argument}")
        if not verdict.valid:
            print(f"  reason: {verdict.reason}")
