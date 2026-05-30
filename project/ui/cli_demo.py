from typing import List, Optional, Tuple

from project.common.types import CandidateArgument, NPCReaction, VerifierResult
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


def print_player_choices(results: List[Tuple[CandidateArgument, VerifierResult]]) -> List[CandidateArgument]:
    valid_candidates = [candidate for candidate, verdict in results if verdict.valid]
    print("\n=== Player Choices ===")
    if not valid_candidates:
        print("- none available")
        return []

    for index, candidate in enumerate(valid_candidates, start=1):
        print(f"{index}. {candidate.strategy}: {_strip_leading_tag(candidate.argument)}")

    return valid_candidates


def choose_candidate(valid_candidates: List[CandidateArgument]) -> Optional[CandidateArgument]:
    if not valid_candidates:
        return None

    while True:
        raw_choice = input("Choose a candidate by number: ").strip()
        try:
            choice = int(raw_choice)
        except ValueError:
            print("Please enter a number.")
            continue

        if 1 <= choice <= len(valid_candidates):
            return valid_candidates[choice - 1]

        print(f"Choose a number between 1 and {len(valid_candidates)}.")


def print_reactions(reactions: List[NPCReaction]) -> None:
    if not reactions:
        return

    print("\n=== NPC Reactions ===")
    for reaction in reactions:
        print(f"- {reaction.npc_name} [{reaction.role}] mood={reaction.mood}")
        print(f"  {reaction.text}")
