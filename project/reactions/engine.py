from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from project.adaptation.config import AdaptationConfig
from project.common.types import CandidateArgument, NPCReaction, VerifierResult


def _pick_first(items: Iterable[str], default: str) -> str:
    for item in items:
        if item:
            return item
    return default


def _get_statement(bundle: Dict, statement_id: str) -> Dict:
    testimonies = bundle.get("testimonies", {})
    for statement in testimonies.get("statements", []):
        if statement.get("id") == statement_id:
            return statement
    return {}


def _get_target_witness(bundle: Dict) -> Dict:
    testimony_id = bundle.get("testimonies", {}).get("id")
    testimony = bundle.get("testimonies", {})
    witness_id = testimony.get("witness_id")
    if not witness_id:
        return {}
    witnesses = bundle.get("witnesses", {})
    return witnesses.get(witness_id, {})


def _judge_reaction(bundle: Dict, candidate: CandidateArgument, verdict: VerifierResult) -> NPCReaction:
    judge = bundle.get("judge", {})
    templates = judge.get("reaction_templates", {})
    if verdict.valid:
        text = _pick_first(
            templates.get("correct_objection", []),
            "The court notes the contradiction.",
        )
        mood = "approving"
        trigger = "valid_choice"
    else:
        text = _pick_first(
            templates.get("wrong_objection", []),
            "This objection lacks foundation.",
        )
        mood = "stern"
        trigger = "invalid_choice"

    if verdict.valid:
        if candidate.strategy == "timeline":
            text = f"{text} The timing matters here."
        elif candidate.strategy == "credibility":
            text = f"{text} The witness's reliability is now in question."
        elif candidate.strategy == "forensic":
            text = f"{text} The physical record is being weighed appropriately."
        elif candidate.strategy == "logic":
            text = f"{text} The reasoning chain is acceptable."
        elif candidate.strategy == "court-record":
            text = f"{text} The record must stay precise."

    return NPCReaction(
        npc_id=judge.get("id", "judge"),
        npc_name=judge.get("name", "Judge"),
        role="judge",
        trigger=trigger,
        mood=mood,
        text=text,
    )


def _witness_reaction(bundle: Dict, candidate: CandidateArgument, verdict: VerifierResult) -> Optional[NPCReaction]:
    witness = _get_target_witness(bundle)
    if not witness:
        return None

    statement = _get_statement(bundle, candidate.target_statement_id)
    statement_emotion = statement.get("emotion", "neutral")
    press_response = statement.get("press_response", "")
    behavior_rules = witness.get("behavior_rules", [])
    speech_style = witness.get("speech_style", {})
    honesty = witness.get("personality", {}).get("honesty", 5)
    anxiety = witness.get("personality", {}).get("anxiety", 5)

    if verdict.valid:
        if statement_emotion in {"defensive", "nervous"} or anxiety >= 7:
            mood = "cornered"
            trigger = "challenged_statement"
            text = press_response or "I... I don't know what to say to that."
        else:
            mood = "uneasy"
            trigger = "challenged_statement"
            text = "That does not prove what you think it proves."
    else:
        mood = "confident"
        trigger = "rebutted_choice"
        if honesty <= 4:
            text = "See? That is not what happened at all."
        else:
            text = "That argument does not fit the facts."

    if behavior_rules:
        first_rule = behavior_rules[0].lower()
        if "eye contact" in first_rule and verdict.valid:
            text = f"{text} The witness avoids eye contact."
        elif "cornered" in first_rule and verdict.valid:
            text = f"{text} {press_response}".strip()

    if speech_style.get("formality", 0) >= 7:
        text = f"{text}"
    elif speech_style.get("verbose"):
        text = f"{text} There is more to this than it seems."

    return NPCReaction(
        npc_id=witness.get("id", "witness"),
        npc_name=witness.get("name", "Witness"),
        role="witness",
        trigger=trigger,
        mood=mood,
        text=text,
    )


def build_npc_reactions(
    bundle: Dict,
    candidate: CandidateArgument,
    verdict: VerifierResult,
    adaptation: AdaptationConfig,
) -> List[NPCReaction]:
    reactions: List[NPCReaction] = []
    judge_reaction = _judge_reaction(bundle, candidate, verdict)
    reactions.append(judge_reaction)

    witness_reaction = _witness_reaction(bundle, candidate, verdict)
    if witness_reaction is not None:
        reactions.append(witness_reaction)

    if adaptation.hint_level > 0.7 and verdict.valid:
        reactions.append(
            NPCReaction(
                npc_id=bundle.get("prosecutor", {}).get("id", "prosecutor"),
                npc_name=bundle.get("prosecutor", {}).get("name", "Prosecutor"),
                role="prosecutor",
                trigger="reinforcement",
                mood="focused",
                text="Good. Keep pressing that contradiction.",
            )
        )

    return reactions
