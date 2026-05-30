from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Any

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
    history: Optional[List[Dict]] = None,
    ollama_model: str = "llama3:8b",
) -> List[NPCReaction]:
    """Build NPC reactions. Prefer generating contextual reactions via Ollama when available,
    otherwise fall back to template-driven responses.

    `history` is a list of prior player choice dicts (trial_state.player_choices).
    """
    # Try LLM-driven reactions first (best-effort)
    try:
        import importlib

        mod = importlib.import_module("project.generation.ollama_client")
        ollama_generate_json = getattr(mod, "ollama_generate_json", None)
    except Exception:
        ollama_generate_json = None

    if ollama_generate_json is not None:
        try:
            # Build a compact context payload
            ctx_lines: List[str] = []
            ctx_lines.append(f"Case: {bundle.get('case', {}).get('id')} - {bundle.get('case', {}).get('title')}")
            ctx_lines.append(f"Phase: {bundle.get('case', {}).get('phases', [])}")
            # last candidate summary
            cand_summary = {
                "candidate_id": getattr(candidate, "candidate_id", None) or getattr(candidate, "candidate_id", None) or getattr(candidate, "candidate_id", None)
            }
            ctx_lines.append(f"Candidate: strategy={getattr(candidate, 'strategy', '')} argument={getattr(candidate, 'argument', '')}")
            if history:
                ctx_lines.append("Prior choices:")
                for h in history:
                    ctx_lines.append(f"- {h.get('candidate_id')} strategy={h.get('strategy')} argument={h.get('argument') or h.get('presented_argument')}")

            prompt = (
                "<<<JSON_START>>>" +
                "[\n" +
                "  {\"npc\": \"judge\", \"role\": \"judge\", \"instruction\": \"Respond as the judge to the presented argument and prior dialog. Keep it concise.\"},\n" +
                "  {\"npc\": \"witness\", \"role\": \"witness\", \"instruction\": \"Respond as the witness to being challenged; include behavioral cues if appropriate.\"},\n" +
                "  {\"npc\": \"prosecutor\", \"role\": \"prosecutor\", \"instruction\": \"Respond as the prosecutor, either rebutting or supporting based on the presented argument.\"}\n" +
                "]" +
                "<<<JSON_END>>>"
            )

            # Provide a helper textual prompt including context and desired JSON schema
            llm_prompt = (
                f"You are simulating courtroom NPC reactions.\n\nCONTEXT:\n" + "\n".join(ctx_lines) +
                "\n\nTASK: For each NPC (judge, witness, prosecutor) produce an object with keys: npc_name, role, trigger, mood, text."
                " Return a JSON array of objects exactly as the values (no extra commentary)."
                " Surround JSON with <<<JSON_START>>> and <<<JSON_END>>>."
            )

            parsed = ollama_generate_json(prompt=llm_prompt, model=ollama_model, temperature=adaptation.temperature)
            if isinstance(parsed, list) and parsed:
                reactions: List[NPCReaction] = []
                for obj in parsed:
                    if not isinstance(obj, dict):
                        continue
                    npc_id = obj.get("npc_name", obj.get("npc", obj.get("role", "npc")))
                    npc_name = obj.get("npc_name", npc_id)
                    role = obj.get("role", "npc")
                    trigger = obj.get("trigger", "response")
                    mood = obj.get("mood", "neutral")
                    text = obj.get("text", "")
                    reactions.append(NPCReaction(npc_id=npc_id, npc_name=npc_name, role=role, trigger=trigger, mood=mood, text=text))
                if reactions:
                    return reactions
        except Exception as e:
            print(f"[debug] LLM-driven NPC reactions failed: {e}")

    # Fallback to template-based reactions
    reactions: List[NPCReaction] = []
    judge_reaction = _judge_reaction(bundle, candidate, verdict)
    reactions.append(judge_reaction)

    witness_reaction = _witness_reaction(bundle, candidate, verdict)
    if witness_reaction is not None:
        reactions.append(witness_reaction)

    # Prosecutor should react oppositely to the defense: if defendant's contradiction is valid,
    # prosecutor will attempt to rebut; if invalid, prosecutor will push the advantage.
    prosecutor = bundle.get("prosecutor", {})
    proc_templates = prosecutor.get("reaction_templates", {})
    if verdict.valid:
        # construct a counterargument text using templates if available
        counter_text = None
        if proc_templates.get("counter_objection"):
            counter_text = proc_templates.get("counter_objection")[0]
        else:
            counter_text = "Objection — the evidence does not support that inference, Your Honor."
        reactions.append(
            NPCReaction(
                npc_id=prosecutor.get("id", "prosecutor"),
                npc_name=prosecutor.get("name", "Prosecutor"),
                role="prosecutor",
                trigger="counter",
                mood="combative",
                text=counter_text,
            )
        )
    else:
        support_text = None
        if proc_templates.get("support_objection"):
            support_text = proc_templates.get("support_objection")[0]
        else:
            support_text = "The court should note that the prosecution's evidence remains compelling."
        reactions.append(
            NPCReaction(
                npc_id=prosecutor.get("id", "prosecutor"),
                npc_name=prosecutor.get("name", "Prosecutor"),
                role="prosecutor",
                trigger="support",
                mood="confident",
                text=support_text,
            )
        )

    return reactions
