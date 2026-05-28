from typing import List, Tuple

from project.common.types import CandidateArgument, VerifierResult
import re


def _strip_leading_tag(text: str) -> str:
    # remove leading bracketed tags like [timeline-pressure/neutral]
    return re.sub(r'^\s*\[.*?\]\s*', '', text)


def print_candidates(results: List[Tuple[CandidateArgument, VerifierResult]]) -> None:
    print("\n=== Verified Candidates ===")
    for candidate, verdict in results:
        status = "OK" if verdict.valid else "REJECT"
        print(f"- {candidate.candidate_id} [{status}] strategy={candidate.strategy}")
        # print only the human-facing argument text (strip internal tags)
        print(f"  {_strip_leading_tag(candidate.argument)}")
        if not verdict.valid:
            print(f"  reason: {verdict.reason}")
