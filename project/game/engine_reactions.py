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
    # support several testimony shapes: list, single dict with 'statements', or dict of testimony objects
    if isinstance(testimonies, list):
        for testimony in testimonies:
            for statement in testimony.get("statements", []):
                if statement.get("id") == statement_id:
                    return statement
    elif isinstance(testimonies, dict):
        # single testimony object
        if testimonies.get("statements"):
            for statement in testimonies.get("statements", []):
                if statement.get("id") == statement_id:
                    return statement
        # dict mapping ids -> testimony objects
        for testimony in testimonies.values():
            if not isinstance(testimony, dict):
                continue
            for statement in testimony.get("statements", []):
                if statement.get("id") == statement_id:
                    return statement
    return {}


def _get_target_witness(bundle: Dict, statement_id: Optional[str] = None) -> Dict:
    """Find the witness object related to a statement id (if provided).

    Falls back to top-level testimony->witness mapping when a direct match is not found.
    """
    testimonies = bundle.get("testimonies", {})
    witness_id = None

    # If a statement_id is provided, search for the testimony that contains it
    if statement_id:
        if isinstance(testimonies, list):
            for testimony in testimonies:
                for stmt in testimony.get("statements", []):
                    if stmt.get("id") == statement_id:
                        witness_id = testimony.get("witness_id")
                        break
                if witness_id:
                    break
        elif isinstance(testimonies, dict):
            if testimonies.get("statements"):
                for stmt in testimonies.get("statements", []):
                    if stmt.get("id") == statement_id:
                        witness_id = testimonies.get("witness_id")
                        break
            if not witness_id:
                for testimony in testimonies.values():
                    if not isinstance(testimony, dict):
                        continue
                    for stmt in testimony.get("statements", []):
                        if stmt.get("id") == statement_id:
                            witness_id = testimony.get("witness_id")
                            break
                    if witness_id:
                        break

    # fallback: if no statement-based witness found, try a top-level mapping
    if not witness_id:
        testimony = testimonies if isinstance(testimonies, dict) else (testimonies[0] if testimonies else {})
        witness_id = testimony.get("witness_id") if isinstance(testimony, dict) else None

    if not witness_id:
        return {}

    witnesses = bundle.get("witnesses", {})
    # witnesses may be list or dict
    if isinstance(witnesses, dict):
        return witnesses.get(witness_id, {})
    if isinstance(witnesses, list):
        for w in witnesses:
            if w.get("id") == witness_id:
                return w
    return {}


def _find_evidence(bundle: Dict, evidence_id: Optional[str]) -> Dict:
    """Try common locations in the bundle to find an evidence object by id."""
    if not evidence_id:
        return {}
    # common keys to search
    keys = ["evidence", "evidences", "evidence_items", "evidence_list", "evidence_set"]
    for key in keys:
        collection = bundle.get(key)
        if isinstance(collection, dict):
            # direct object
            if collection.get("id") == evidence_id:
                return collection
            if collection.get(evidence_id):
                return collection.get(evidence_id)
            # maybe dict of objects
            for v in collection.values():
                if isinstance(v, dict) and v.get("id") == evidence_id:
                    return v
        elif isinstance(collection, list):
            for item in collection:
                if isinstance(item, dict) and item.get("id") == evidence_id:
                    return item

    # also check top-level case block
    case_block = bundle.get("case", {}) or {}
    for key in ("evidences", "evidence"):
        collection = case_block.get(key)
        if isinstance(collection, dict) and collection.get(evidence_id):
            return collection.get(evidence_id)
        if isinstance(collection, list):
            for item in collection:
                if item.get("id") == evidence_id:
                    return item

    return {}


def _prosecutor_question_for_candidate(
    bundle: Dict,
    candidate: CandidateArgument,
    verdict: VerifierResult,
    *,
    publicly_seen_statement_ids: Optional[List[str]] = None,
) -> str:
    """Generate a focused prosecutor question targeting the *presented argument*.

    In ARGUMENTATION the prosecutor reacts to what the defense just said out loud.
    We NEVER quote a statement that has not yet been publicly challenged in
    cross-examination (i.e. that is not in `publicly_seen_statement_ids`).

    `publicly_seen_statement_ids` is the list of statement ids that the player
    has *already* selected and argued in CROSS_EXAMINATION (from history).
    """
    evidence = _find_evidence(bundle, getattr(candidate, "evidence_id", None))
    evidence_name = evidence.get("name") or evidence.get("id") or "the evidence"

    target_sid = getattr(candidate, "target_statement_id", None)
    seen = set(publicly_seen_statement_ids or [])
    stmt_is_public = target_sid in seen

    # The argument text the defense just presented — react to *this*, not to internal data.
    argument_text = (getattr(candidate, "argument", "") or "").strip()

    # If the defense presented physical evidence, challenge whether it actually proves intent.
    if getattr(candidate, "present_evidence", False) and evidence:
        return (
            f"Objection. Counsel claims {evidence_name} undermines my witness, "
            f"but presenting an item does not establish who knew what. "
            f"Witness — did you directly observe the defendant handle that item, "
            f"or are you drawing an inference from what you saw?"
        )

    # If the targeted statement was publicly cross-examined we can reference it.
    if stmt_is_public:
        stmt = _get_statement(bundle, target_sid)
        stmt_text = (stmt.get("text") or "").strip()
        if stmt_text:
            return (
                f"Objection. Counsel is mischaracterising my witness. "
                f"Witness, you stated: '{stmt_text}'. "
                f"Is that still your testimony, and does anything the defense just argued change what you personally observed?"
            )

    # Generic fallback — react only to the argument content, never reveal unseen statements.
    if argument_text:
        # truncate to avoid overly long quotes
        snippet = argument_text if len(argument_text) <= 120 else argument_text[:117] + "..."
        return (
            f"Objection. The defense argues: '{snippet}' — "
            f"but that is speculation. Witness, does anything you personally observed support that alternative?"
        )

    return "Objection. The defense's argument is speculative and not grounded in what the witness actually saw."


def _witness_answer_to_question(
    bundle: Dict,
    candidate: CandidateArgument,
    verdict: VerifierResult,
    question: str,
    *,
    publicly_seen_statement_ids: Optional[List[str]] = None,
) -> str:
    """Craft a concise witness answer to the prosecutor's challenge.

    Only references the specific statement text when that statement has been
    publicly argued in cross-examination (`publicly_seen_statement_ids`).
    """
    target_sid = getattr(candidate, "target_statement_id", None)
    seen = set(publicly_seen_statement_ids or [])
    stmt_is_public = target_sid in seen

    stmt = _get_statement(bundle, target_sid)
    press_response = (stmt.get("press_response") or "").strip()
    stmt_text = (stmt.get("text") or "").strip()

    witness = _get_target_witness(bundle, target_sid)
    honesty = witness.get("personality", {}).get("honesty", 5)

    if stmt_is_public:
        if press_response:
            return press_response
        if honesty >= 7 and stmt_text:
            return f"I described exactly what I saw: {stmt_text}"
        if stmt_text:
            return f"I stand by what I said. '{stmt_text}' — that is what I witnessed."

    # Statement not yet publicly cross-examined: witness reacts to the defence's argument only.
    if getattr(candidate, "present_evidence", False) and getattr(candidate, "presentation_score", 0.0) >= 0.7:
        return "I'm not sure that item changes anything — I described what I saw clearly at the time."

    if verdict.valid:
        return "That argument raises questions I hadn't considered, I'll admit."

    return "I don't see how what counsel said contradicts my account."


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
        # append a short summary of the defense point for clarity (avoid final-verdict language)
        arg = getattr(candidate, "argument", "") or ""
        if arg:
            snippet = arg if len(arg) <= 160 else arg[:157] + "..."
            text = f"{text} (Defense: {snippet})"
        if candidate.strategy == "timeline":
            text = f"{text} The timing is relevant here."
        elif candidate.strategy == "credibility":
            text = f"{text} The witness's reliability is in question."
        elif candidate.strategy == "forensic":
            text = f"{text} The physical evidence is being weighed."
        elif candidate.strategy == "logic":
            text = f"{text} The logical chain is under review."
        elif candidate.strategy == "court-record":
            text = f"{text} The record must remain precise."

    return NPCReaction(
        npc_id=judge.get("id", "judge"),
        npc_name=judge.get("name", "Judge"),
        role="judge",
        trigger=trigger,
        mood=mood,
        text=text,
    )


def _witness_reaction(bundle: Dict, candidate: CandidateArgument, verdict: VerifierResult) -> Optional[NPCReaction]:
    witness = _get_target_witness(bundle, getattr(candidate, "target_statement_id", None))
    if not witness:
        return None

    statement = _get_statement(bundle, candidate.target_statement_id)
    statement_emotion = statement.get("emotion", "neutral")
    press_response = statement.get("press_response", "")
    behavior_rules = witness.get("behavior_rules", [])
    speech_style = witness.get("speech_style", {})
    honesty = witness.get("personality", {}).get("honesty", 5)
    anxiety = witness.get("personality", {}).get("anxiety", 5)

    # Try to locate the evidence object the candidate references
    evidence = _find_evidence(bundle, getattr(candidate, "evidence_id", None))
    evidence_name = evidence.get("name") or evidence.get("id") or "the evidence"

    trigger = "response"
    # Build more specific witness reactions depending on validity and whether the evidence was presented
    if verdict.valid:
        trigger = "challenged_statement"
        if getattr(candidate, "present_evidence", False):
            # witness is being directly contradicted by evidence
            if statement_emotion in {"defensive", "nervous"} or anxiety >= 7:
                mood = "cornered"
                text = press_response or f"I don't remember {evidence_name} being shown or that the defendant did that."
            else:
                mood = "uneasy"
                text = press_response or f"That doesn't match my memory; I only stated: '{statement.get('text','')}'."
        else:
            mood = "uneasy"
            text = press_response or f"That argument doesn't change the facts I described."
    else:
        trigger = "rebutted_choice"
        mood = "confident"
        if honesty <= 4:
            text = press_response or "You're twisting my words — that's not how it happened."
        else:
            text = press_response or "That argument misstates what I said."

    # apply behavior rules and style nudges
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
    phase: Optional[str] = None,
) -> List[NPCReaction]:
    
    publicly_seen_statement_ids: List[str] = [
        h["target_statement_id"]
        for h in (history or [])
        if h.get("target_statement_id") and h.get("presented_argument")
    ]

    is_argumentation = phase and phase.upper() == "ARGUMENTATION"

    try:
        import importlib
        mod = importlib.import_module("project.generation.ollama_client")
        ollama_generate_json = getattr(mod, "ollama_generate_json", None)
    except Exception:
        ollama_generate_json = None

    if ollama_generate_json is not None:
        try:
            ctx_lines: List[str] = []
            ctx_lines.append(f"Case: {bundle.get('case', {}).get('id')} - {bundle.get('case', {}).get('title')}")
            evidence = _find_evidence(bundle, getattr(candidate, "evidence_id", None))
            evidence_desc = evidence.get("description") or evidence.get("name") or ""
            ctx_lines.append(f"Defense argument just presented: {getattr(candidate, 'argument', '')}")
            ctx_lines.append(f"Strategy: {getattr(candidate, 'strategy', '')}  Evidence: {evidence.get('name', '')}")
            
            # ─── CORREÇÃO 3: INJECTAR SE A JOGADA É VALIDA OU NÃO NO PROMPT ───
            ctx_lines.append(f"Is Defense Argument Valid/True?: {verdict.valid}")
            
            if evidence_desc:
                ctx_lines.append(f"Evidence detail: {evidence_desc}")
            if phase:
                ctx_lines.append(f"Phase: {phase}")
            if history:
                ctx_lines.append("Prior presented arguments (in order):")
                for h in history:
                    presented = h.get("presented_argument") or h.get("argument")
                    if presented:
                        ctx_lines.append(f"  - {presented}")

            llm_prompt = (
                "You are simulating courtroom NPC reactions in a legal game similar to Ace Attorney.\n\n"
                "CONTEXT:\n" + "\n".join(ctx_lines) +
                "\n\nRULES:\n"
                "- The prosecutor reacts to the defense argument that was JUST presented.\n"
                "- If 'Is Defense Argument Valid' is True, the prosecutor should feel pressured/angry, and the witness uneasy.\n"
                "- If 'Is Defense Argument Valid' is False, the prosecutor should be confident and mock the defense.\n"
                "- Do NOT quote or reference testimony statements that have not been mentioned above.\n"
                "- Keep each reaction to 1-2 sentences, natural courtroom speech.\n\n"
                "TASK: Return a JSON array with objects for: prosecutor, witness. "
                "Each object: {npc_name, role, trigger, mood, text}. "
                "Surround with <<<JSON_START>>> and <<<JSON_END>>>."
            )

            # ... (código anterior do prompt e parsing do ollama) ...
            parsed = ollama_generate_json(prompt=llm_prompt, model=ollama_model, temperature=adaptation.temperature)
            if isinstance(parsed, list) and parsed:
                reactions: List[NPCReaction] = []
                for obj in parsed:
                    if not isinstance(obj, dict):
                        continue
                    
                    # Forçamos tudo para minúsculas para não haver falhas de mapeamento!
                    role = str(obj.get("role", obj.get("npc_name", "npc"))).strip().lower()
                    
                    # Se a IA devolver o nome "Prosecutor", convertemos o role interno para "prosecutor"
                    if "prosecutor" in role or "valen" in role:
                        role = "prosecutor"
                    elif "witness" in role or "cashier" in role or "line" in role:
                        role = "witness"
                        
                    npc_name = obj.get("npc_name", role.capitalize())
                    npc_id = role
                    trigger = obj.get("trigger", "response")
                    mood = obj.get("mood", "neutral")
                    text = obj.get("text", "")
                    
                    reactions.append(NPCReaction(npc_id=npc_id, npc_name=npc_name, role=role, trigger=trigger, mood=mood, text=text))
                
                if reactions:
                    role_map = {r.role.lower(): r for r in reactions}

                    if is_argumentation:
                        if "prosecutor" not in role_map:
                            proc_q = _prosecutor_question_for_candidate(bundle, candidate, verdict, publicly_seen_statement_ids=publicly_seen_statement_ids)
                            prosecutor = bundle.get("prosecutor", {})
                            reactions.append(NPCReaction(
                                npc_id=prosecutor.get("id", "prosecutor"),
                                npc_name=prosecutor.get("name", "Prosecutor"),
                                role="prosecutor", trigger="question",
                                mood="combative" if verdict.valid else "inquisitive",
                                text=proc_q,
                            ))
                        if "witness" not in role_map:
                            w_text = _witness_answer_to_question(bundle, candidate, verdict, getattr(candidate, "argument", ""), publicly_seen_statement_ids=publicly_seen_statement_ids)
                            witness = _get_target_witness(bundle, getattr(candidate, "target_statement_id", None))
                            if w_text:
                                reactions.append(NPCReaction(
                                    npc_id=witness.get("id", "witness"),
                                    npc_name=witness.get("name", "Witness"),
                                    role="witness", trigger="answer", mood="uneasy", text=w_text,
                                ))
                    
                    return reactions
                    
        except Exception as e:
            print(f"[debug] LLM-driven NPC reactions failed: {e}")

    # ── Template fallback ────────────────────────────────────────────────────
    reactions: List[NPCReaction] = []

    if is_argumentation:
        prosecutor = bundle.get("prosecutor", {})
        proc_q = _prosecutor_question_for_candidate(
            bundle, candidate, verdict,
            publicly_seen_statement_ids=publicly_seen_statement_ids,
        )
        reactions.append(NPCReaction(
            npc_id=prosecutor.get("id", "prosecutor"),
            npc_name=prosecutor.get("name", "Prosecutor"),
            role="prosecutor", trigger="question",
            mood="combative" if verdict.valid else "inquisitive",
            text=proc_q,
        ))

        witness = _get_target_witness(bundle, getattr(candidate, "target_statement_id", None))
        w_text = _witness_answer_to_question(
            bundle, candidate, verdict, proc_q,
            publicly_seen_statement_ids=publicly_seen_statement_ids,
        )
        if witness and w_text:
            reactions.append(NPCReaction(
                npc_id=witness.get("id", "witness"),
                npc_name=witness.get("name", "Witness"),
                role="witness", trigger="answer", mood="uneasy", text=w_text,
            ))

        proc_templates = prosecutor.get("reaction_templates", {})
        if verdict.valid:
            counter_text = proc_templates.get("counter_objection", ["Objection — the evidence does not support that inference, Your Honor."])[0]
            reactions.append(NPCReaction(npc_id=prosecutor.get("id", "prosecutor"), npc_name=prosecutor.get("name", "Prosecutor"), role="prosecutor", trigger="counter", mood="combative", text=counter_text))
        else:
            support_text = proc_templates.get("support_objection", ["The court should note that the prosecution's evidence remains compelling."])[0]
            reactions.append(NPCReaction(npc_id=prosecutor.get("id", "prosecutor"), npc_name=prosecutor.get("name", "Prosecutor"), role="prosecutor", trigger="support", mood="confident", text=support_text))

        return reactions

    # Default non-argumentation fallback: judge -> witness -> prosecutor
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
