from __future__ import annotations

import argparse
import json
import time
import re
from pathlib import Path
from project.adaptation.config import AdaptationConfig
from project.common.types import TrialContext
from project.generation.candidate_generator import generate_candidates
from project.logs.logger import append_log
from project.reactions.engine import build_npc_reactions
from project.prompts.prompt_builder import build_prompt
from project.retrieval.loader import build_documents, load_case_bundle
from project.retrieval.store import LocalRetriever
from project.ui.cli_demo import choose_candidate, print_player_choices, print_reactions
from project.verifier.symbolic_verifier import verify_candidate
from project.retrieval.chroma_indexer import ensure_chroma_index, build_chroma_retriever
from project.trial.state import TrialState

from project.common.log_events import log_argument_options, log_dialogue, log_evidence


def _iter_testimonies(bundle: dict) -> list[dict]:
    testimonies_obj = bundle.get("testimonies", {})
    if isinstance(testimonies_obj, list):
        return [item for item in testimonies_obj if isinstance(item, dict)]
    if isinstance(testimonies_obj, dict):
        if testimonies_obj.get("statements"):
            return [testimonies_obj]
        return [item for item in testimonies_obj.values() if isinstance(item, dict)]
    return []


def _resolve_testimony(bundle: dict, testimony_id: str | None = None, witness_id: str | None = None) -> dict:
    testimonies = _iter_testimonies(bundle)
    if testimony_id:
        for testimony in testimonies:
            if testimony.get("id") == testimony_id:
                return testimony
    if witness_id:
        for testimony in testimonies:
            if testimony.get("witness_id") == witness_id:
                return testimony
    return testimonies[0] if testimonies else {}


def _print_case_snapshot(bundle: dict) -> None:
    case = bundle.get("case", {})
    evidence_items = bundle.get("evidence", {})
    testimony_items = _iter_testimonies(bundle)
    witness_items = bundle.get("witnesses", {})
    truth = bundle.get("truth", {})

    if isinstance(evidence_items, dict):
        evidence_ids = [item.get("id") for item in evidence_items.values() if isinstance(item, dict) and item.get("id")]
    else:
        evidence_ids = [item.get("id") for item in evidence_items if isinstance(item, dict) and item.get("id")]

    testimony_ids = [item.get("id") for item in testimony_items if item.get("id")]
    witness_ids = [item.get("id") for item in witness_items.values() if isinstance(item, dict) and item.get("id")]

    print("Loaded case snapshot:")
    print(f"- case_id: {case.get('id')}")
    print(f"- title: {case.get('title')}")
    print(f"- difficulty: {case.get('difficulty')}")
    print(f"- evidence_count: {len(evidence_ids)} -> {', '.join(evidence_ids) if evidence_ids else '(none)'}")
    print(f"- testimony_count: {len(testimony_ids)} -> {', '.join(testimony_ids) if testimony_ids else '(none)'}")
    print(f"- witness_count: {len(witness_ids)} -> {', '.join(witness_ids) if witness_ids else '(none)'}")
    print(f"- truth_facts: {len(truth.get('facts', []))}")
    print(f"- truth_timeline_events: {len(truth.get('timeline', []))}")


def run_pipeline(
    repo_root: Path,
    case_id: str,
    query: str,
    tone: str,
    k: int,
    retrieval_k: int,
    use_chroma: bool,
    use_ollama: bool = True,
    ollama_model: str = "llama3:8b",
    hint_level: float = 0.9,
    force_reindex: bool = False,
) -> None:
    start = time.perf_counter()

    bundle = load_case_bundle(repo_root, case_id)
    docs = build_documents(bundle)

    # initialize retrieval and trial state
    retriever = None
    if use_chroma:
        ensure_chroma_index(repo_root, case_id, docs, force=force_reindex)
        retriever = build_chroma_retriever(case_id)
    if retriever is None:
        retriever = LocalRetriever(docs)

    adaptation = AdaptationConfig(tone=tone, difficulty=int(bundle["case"].get("difficulty", 1)), hint_level=hint_level)

    trial_state = TrialState(bundle, log_file=repo_root / "project" / "logs" / "runtime.jsonl")
    # start at the first phase defined in the case
    first_phase = bundle["case"].get("phases", [])[0]
    current_phase_id = first_phase.get("id")

    # simple game loop following case phases
    while current_phase_id is not None:
        phase = trial_state.phases.get(current_phase_id, {})
        phase_type = phase.get("type")
        print(f"\n--- Phase: {current_phase_id} ({phase_type}) ---")

        if phase_type == "INTRO":
            _print_case_snapshot(bundle)
            print(bundle["case"].get("summary", ""))

            log_dialogue(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                speaker="Narrator",
                text=bundle["case"].get("summary", ""),
                source="cli",
            )

            next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "INVESTIGATION":
            locations = phase.get("locations", [])
            print("Available locations:", ", ".join(locations))
            log_evidence(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                title="Available locations",
                description=f"{', '.join(locations)}",
                source="cli",
            )
            next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "TESTIMONY":
            testimony_id = phase.get("testimony_id")
            witness_id = phase.get("witness_id")
            testimony = _resolve_testimony(bundle, testimony_id=testimony_id, witness_id=witness_id)
            print("Testimony:")
            for stmt in testimony.get("statements", []):
                print(f"- {stmt.get('id')}: {stmt.get('text')}")

                log_dialogue(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    speaker="Witness",
                    text=stmt.get('text'),
                    source="cli"
                )

            next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "CROSS_EXAMINATION":
            # Let player choose which statement to challenge (cross-examination)
            testimony_id = phase.get("testimony_id")
            witness_id = phase.get("witness_id")
            testimonies_obj = bundle.get("testimonies", {})

            # testimonies may be a single dict (as in cases/testimonies.json) or a mapping
            testimony = None
            if isinstance(testimonies_obj, dict) and testimonies_obj.get("id") == testimony_id:
                testimony = testimonies_obj
            elif isinstance(testimonies_obj, dict) and testimony_id and testimony_id in testimonies_obj:
                testimony = testimonies_obj.get(testimony_id)
            elif isinstance(testimonies_obj, list):
                for t in testimonies_obj:
                    if t.get("id") == testimony_id or (witness_id and t.get("witness_id") == witness_id):
                        testimony = t
                        break
            else:
                # fallback: if it's a dict but not keyed by id, try to match by witness_id
                if isinstance(testimonies_obj, dict) and witness_id and testimonies_obj.get("witness_id") == witness_id:
                    testimony = testimonies_obj

            statements = (testimony or {}).get("statements", [])
            if not statements:
                print("No statements available for cross-examination.")
                log_argument_options(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    options="No statements available for cross-examination",
                    source="cli",
                )
                next_phase_id = trial_state.next_phase_id(current_phase_id)
            else:
                print("Statements available to challenge:")
                for idx, stmt in enumerate(statements, start=1):
                    print(f"{idx}. {stmt.get('id')}: {stmt.get('text')}")
                log_argument_options(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    options=statements,
                    source="cli",
                )

                # choose statement by number
                proceed_to_final = False
                while True:
                    raw = input("Choose a statement to challenge by number (or Enter to skip): ").strip()
                    if raw == "":
                        # Ask whether to proceed to final defense or continue cross-exam
                        yn = input("No statement chosen. Proceed to final defense? (y/n): ").strip().lower()
                        if yn in {"y", "yes"}:
                            chosen_stmt = None
                            proceed_to_final = True
                            break
                        else:
                            # re-prompt the statement selection
                            continue
                    try:
                        n = int(raw)
                    except ValueError:
                        print("Please enter a number or blank to skip.")
                        continue
                    if 1 <= n <= len(statements):
                        chosen_stmt = statements[n - 1]
                        break
                    print(f"Choose a number between 1 and {len(statements)}.")

                if not chosen_stmt:
                    if proceed_to_final:
                        # find final_defense phase id
                        final_phase_id = None
                        for pid, p in trial_state.phases.items():
                            if p.get("type") == "FINAL_DEFENSE":
                                final_phase_id = pid
                                break
                        next_phase_id = final_phase_id or trial_state.next_phase_id(current_phase_id)
                    else:
                        next_phase_id = trial_state.next_phase_id(current_phase_id)
                else:
                    # run retrieval and candidate generation focused on the chosen statement
                    target_text = chosen_stmt.get("text")
                    retrieved = retriever.similarity_search(target_text or query, k=retrieval_k)
                    context = TrialContext(
                        case_id=bundle["case"]["id"],
                        case_title=bundle["case"]["title"],
                        summary=bundle["case"]["summary"],
                        current_phase=current_phase_id,
                        player_action=target_text,
                    )
                    prompt = build_prompt(context=context, adaptation=adaptation, retrieved=retrieved)
                    candidates = generate_candidates(
                        bundle=bundle,
                        adaptation=adaptation,
                        k=k,
                        prompt=prompt,
                        use_ollama=use_ollama,
                        ollama_model=ollama_model,
                    )

                    verified = [(cand, verify_candidate(bundle, cand, retrieved=retrieved)) for cand in candidates]
                    player_choices = print_player_choices(verified)
                    log_argument_options(
                        repo_root / "project" / "logs" / "runtime.jsonl",
                        case_id=case_id,
                        options=[{"index": index, "text": re.sub(r'^\s*\[.*?\]\s*', '', candidate.argument), "intent": candidate.strategy } for index, candidate in enumerate(player_choices, start=1)],
                        source="cli",
                    )
                    selected_candidate = choose_candidate(player_choices)

                    if selected_candidate is not None:
                        selected_verdict = next((verdict for cand, verdict in verified if cand.candidate_id == selected_candidate.candidate_id), None)
                        if selected_verdict is not None:
                            # persist the player's choice in trial state
                            trial_state.record_choice(selected_candidate, selected_verdict)
                            print(f"\nSelected candidate: {selected_candidate.candidate_id} [{selected_candidate.strategy}]")
                            log_dialogue(
                                repo_root / "project" / "logs" / "runtime.jsonl",
                                case_id=case_id,
                                speaker="Player",
                                text=selected_candidate.argument,
                                source="cli_choice",
                            )
                            reactions = build_npc_reactions(
                                bundle=bundle,
                                candidate=selected_candidate,
                                verdict=selected_verdict,
                                adaptation=adaptation,
                                history=trial_state.player_choices,
                                ollama_model=ollama_model,
                            )
                            for r in reactions:
                                print(f"[REACTION] {r.npc_name} ({r.role}): {r.text}")
                                log_dialogue(
                                    repo_root / "project" / "logs" / "runtime.jsonl",
                                    case_id=case_id,
                                    speaker=r.role,
                                    text=r.text,
                                    source="cli_reaction",
                                )

                            # move to argumentation so player can present/polish their selected argument
                            # find argumentation phase id if present
                            arg_phase_id = None
                            for pid, p in trial_state.phases.items():
                                if p.get("type") == "ARGUMENTATION":
                                    arg_phase_id = pid
                                    break
                            next_phase_id = arg_phase_id or trial_state.next_phase_id(current_phase_id)
                    else:
                        next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "JUDGE_REACTION":
            # show judge reaction templates for demo
            judge = bundle.get("judge", {})
            templates = judge.get("reaction_templates", {})
            print("Judge reactions available:")
            for k, arr in templates.items():
                print(f"- {k}: {arr}")
                log_dialogue(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    speaker="Judge",
                    text=f"{k}': {arr}",
                    source="cli_judge_reactions",
                )
            next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "ARGUMENTATION":
            # Allow the player to present a polished argument based on their chosen candidate(s).
            last_choice = trial_state.player_choices[-1] if trial_state.player_choices else None
            # If there is no immediate last choice, generate discussion candidates based on prior history
            if last_choice is None and trial_state.player_choices:
                prior_context_lines = []
                for i, c in enumerate(trial_state.player_choices, start=1):
                    line = f"choice_{i}: strategy={c.get('strategy')} target={c.get('target_statement_id')} argument={c.get('argument') or c.get('presented_argument')} verdict={c.get('verdict_valid')}"
                    prior_context_lines.append(line)
                player_context = "\n".join(prior_context_lines)
                action_text = bundle.get("case", {}).get("summary", "")
                retrieved = retriever.similarity_search(player_context or action_text, k=retrieval_k)
                context = TrialContext(
                    case_id=bundle["case"]["id"],
                    case_title=bundle["case"]["title"],
                    summary=bundle["case"]["summary"],
                    current_phase=current_phase_id,
                    player_action=f"Discussion request. Prior choices:\n{player_context}\nCurrent focus: {action_text}",
                )
                prompt = build_prompt(context=context, adaptation=adaptation, retrieved=retrieved)
                candidates = generate_candidates(
                    bundle=bundle,
                    adaptation=adaptation,
                    k=k,
                    prompt=prompt,
                    use_ollama=use_ollama,
                    ollama_model=ollama_model,
                )

                verified = [(cand, verify_candidate(bundle, cand, retrieved=retrieved)) for cand in candidates]
                player_choices = print_player_choices(verified)
                log_argument_options(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    options=[{"index": index, "text": re.sub(r'^\s*\[.*?\]\s*', '', candidate.argument), "intent": candidate.strategy } for index, candidate in enumerate(player_choices, start=1)],
                    source="cli",
                )
                selected_candidate = choose_candidate(player_choices)
                if selected_candidate is not None:
                    selected_verdict = next((verdict for cand, verdict in verified if cand.candidate_id == selected_candidate.candidate_id), None)
                    if selected_verdict is not None:
                        trial_state.record_choice(selected_candidate, selected_verdict)
                        last_choice = trial_state.player_choices[-1]
            selected_text = None
            if last_choice:
                # prefer the candidate's argument if available
                selected_text = last_choice.get("argument")

            # attempt to polish via Ollama (lazy import)
            polished = None
            try:
                import importlib
                mod = importlib.import_module("project.generation.ollama_client")
                ollama_generate_json = getattr(mod, "ollama_generate_json", None)
            except Exception:
                ollama_generate_json = None

            if ollama_generate_json is not None and selected_text:
                arg_prompt = (
                    "<<<JSON_START>>>" +
                    "[ {\"argument\": \"" + selected_text.replace('\\', '\\\\').replace('"', '\\"') + "\"} ]" +
                    "<<<JSON_END>>>"
                )
                try:
                    llm_out = ollama_generate_json(prompt=(
                        f"Polish the following single-line court argument to be concise, persuasive, and natural: {selected_text}\n"
                        "Return a JSON array with one object containing the field 'argument' whose value is the polished line."
                    ), model=ollama_model, temperature=adaptation.temperature)
                    if isinstance(llm_out, list) and llm_out:
                        first = llm_out[0]
                        if isinstance(first, dict):
                            polished = first.get("argument") or first.get("text")
                        elif isinstance(first, str):
                            polished = first
                    elif isinstance(llm_out, dict):
                        polished = llm_out.get("argument") or llm_out.get("text")
                    elif isinstance(llm_out, str):
                        polished = llm_out
                except Exception as e:
                    print("[debug] polishing argument failed:", e)

            final_argument = polished or selected_text or "(no argument available)"
            print("\nPresented argument:")
            log_dialogue(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                speaker="Player",
                text=final_argument,
                source="cli_presented_argument",
            )
            print(final_argument)

            # persist presented argument in trial state
            if trial_state.player_choices:
                trial_state.player_choices[-1]["presented_argument"] = final_argument

            # Generate prosecutor rebuttal (if any) and offer the player a follow-up option
            # attempt to build NPC reactions focused on the last choice
            if last_choice:
                # craft minimal candidate-like object to feed reactions builder
                class _C: pass
                cand_obj = _C()
                cand_obj.candidate_id = last_choice.get("candidate_id")
                cand_obj.strategy = last_choice.get("strategy")
                cand_obj.target_statement_id = last_choice.get("target_statement_id")
                cand_obj.evidence_id = last_choice.get("evidence_id")
                cand_obj.argument = final_argument
                # construct a simple verdict-like object
                class _V: pass
                v_obj = _V()
                v_obj.valid = last_choice.get("verdict_valid")
                v_obj.reason = last_choice.get("verdict_reason")

                reactions = build_npc_reactions(
                    bundle=bundle,
                    candidate=cand_obj,
                    verdict=v_obj,
                    adaptation=adaptation,
                    history=trial_state.player_choices,
                    ollama_model=ollama_model,
                )
                # print prosecutor reactions first
                for r in reactions:
                    if r.role and r.role.upper().startswith("PROSECUTOR"):
                        print(f"[PROSECUTOR] {r.npc_name}: {r.text}")
                        log_dialogue(
                            repo_root / "project" / "logs" / "runtime.jsonl",
                            case_id=case_id,
                            speaker="Prosecutor",
                            text=r.text,
                            source="cli_prosecutor_rebuttal",
                        )

            # ask player whether to make a follow-up argument or proceed to judge
            # determine whether there are remaining statements to examine so we can label option 2 accurately
            cross_phase_id = None
            for pid, p in trial_state.phases.items():
                if p.get("type") == "CROSS_EXAMINATION":
                    cross_phase_id = pid
                    break
            cross_phase = trial_state.phases.get(cross_phase_id, {}) if cross_phase_id else {}
            testimony_id = cross_phase.get("testimony_id")
            witness_id = cross_phase.get("witness_id")
            testimonies_obj = bundle.get("testimonies", {})
            testimony = None
            if isinstance(testimonies_obj, dict) and testimonies_obj.get("id") == testimony_id:
                testimony = testimonies_obj
            elif isinstance(testimonies_obj, dict) and testimony_id and testimony_id in testimonies_obj:
                testimony = testimonies_obj.get(testimony_id)
            elif isinstance(testimonies_obj, list):
                for t in testimonies_obj:
                    if t.get("id") == testimony_id or (witness_id and t.get("witness_id") == witness_id):
                        testimony = t
                        break
            else:
                if isinstance(testimonies_obj, dict) and witness_id and testimonies_obj.get("witness_id") == witness_id:
                    testimony = testimonies_obj

            all_statements = [s.get("id") for s in (testimony or {}).get("statements", [])]
            seen = {c.get("target_statement_id") for c in trial_state.player_choices if c.get("target_statement_id")}
            remaining = [s for s in all_statements if s not in seen]

            option2_label = "2) Back to cross-examination" if remaining else "2) Proceed to judge reaction"

            while True:
                print(f"\nOptions:\n1) Make a follow-up argument\n{option2_label}")
                log_argument_options(
                    repo_root / "project" / "logs" / "runtime.jsonl",
                    case_id=case_id,
                    options=[{"index": 1, "text": "1) Make a follow-up argument"}, {"index": 2, "text": option2_label}],
                    source="cli_followup_option",
                )
                choice = input("Choose 1 or 2: ").strip()
                if choice == "1":
                    # follow-up should run the same candidate-generation pipeline
                    # build a concise player-context string from prior choices
                    prior_context_lines = []
                    for i, c in enumerate(trial_state.player_choices, start=1):
                        line = f"choice_{i}: strategy={c.get('strategy')} target={c.get('target_statement_id')} argument={c.get('argument') or c.get('presented_argument')} verdict={c.get('verdict_valid')}"
                        prior_context_lines.append(line)
                    player_context = "\n".join(prior_context_lines) or "(no prior choices)"

                    # run retrieval around the last presented argument or case summary
                    action_text = last_choice.get("presented_argument") or last_choice.get("argument") or bundle.get("case", {}).get("summary", "")
                    retrieved = retriever.similarity_search(action_text or "", k=retrieval_k)

                    context = TrialContext(
                        case_id=bundle["case"]["id"],
                        case_title=bundle["case"]["title"],
                        summary=bundle["case"]["summary"],
                        current_phase=current_phase_id,
                        player_action=f"Follow-up request. Prior choices:\n{player_context}\nCurrent focus: {action_text}",
                    )

                    prompt = build_prompt(context=context, adaptation=adaptation, retrieved=retrieved)
                    candidates = generate_candidates(
                        bundle=bundle,
                        adaptation=adaptation,
                        k=k,
                        prompt=prompt,
                        use_ollama=use_ollama,
                        ollama_model=ollama_model,
                    )

                    verified = [(cand, verify_candidate(bundle, cand, retrieved=retrieved)) for cand in candidates]
                    player_choices = print_player_choices(verified)
                    log_argument_options(
                        repo_root / "project" / "logs" / "runtime.jsonl",
                        case_id=case_id,
                        options=[{"index": index, "text": re.sub(r'^\s*\[.*?\]\s*', '', candidate.argument), "intent": candidate.strategy } for index, candidate in enumerate(player_choices, start=1)],
                        source="cli",
                    )
                    selected_candidate = choose_candidate(player_choices)

                    if selected_candidate is not None:
                        selected_verdict = next((verdict for cand, verdict in verified if cand.candidate_id == selected_candidate.candidate_id), None)
                        if selected_verdict is not None:
                            trial_state.record_choice(selected_candidate, selected_verdict)
                            print(f"\nSelected candidate: {selected_candidate.candidate_id} [{selected_candidate.strategy}]")
                            reactions = build_npc_reactions(
                                bundle=bundle,
                                candidate=selected_candidate,
                                verdict=selected_verdict,
                                adaptation=adaptation,
                                history=trial_state.player_choices,
                                ollama_model=ollama_model,
                            )
                            for r in reactions:
                                print(f"[REACTION] {r.npc_name} ({r.role}): {r.text}")
                                log_dialogue(
                                    repo_root / "project" / "logs" / "runtime.jsonl",
                                    case_id=case_id,
                                    speaker=r.role,
                                    text=r.text,
                                    source="cli_reaction",
                                )

                            # set last_choice to the new selection for subsequent argumentation steps
                            last_choice = trial_state.player_choices[-1]
                            # do not advance phase; remain in ARGUMENTATION to allow further follow-ups
                            next_phase_id = current_phase_id
                            break
                    else:
                        # no candidates selected; return to options
                        continue
                if choice == "2":
                    # before moving to judge, apply contradiction rules based on last_choice
                    next_phase_id = None
                    if last_choice:
                        next_phase_id, penalty, judge_response = trial_state.apply_contradiction(
                            current_phase=current_phase_id,
                            statement_id=last_choice.get("target_statement_id"),
                            evidence_id=last_choice.get("evidence_id"),
                            success=bool(last_choice.get("verdict_valid")),
                        )
                        if penalty:
                            print(f"Penalty applied: {penalty}")
                        if judge_response:
                            print(f"Judge response key: {judge_response}")

                    # determine remaining statements for this cross-exam phase
                    # find the CROSS_EXAMINATION phase id(s)
                    cross_phase_id = None
                    for pid, p in trial_state.phases.items():
                        if p.get("type") == "CROSS_EXAMINATION":
                            cross_phase_id = pid
                            break

                    # collect all statements from the relevant testimony
                    # attempt to locate the testimony used by the cross phase
                    cross_phase = trial_state.phases.get(cross_phase_id, {}) if cross_phase_id else {}
                    testimony_id = cross_phase.get("testimony_id")
                    witness_id = cross_phase.get("witness_id")
                    testimonies_obj = bundle.get("testimonies", {})
                    testimony = None
                    if isinstance(testimonies_obj, dict) and testimonies_obj.get("id") == testimony_id:
                        testimony = testimonies_obj
                    elif isinstance(testimonies_obj, dict) and testimony_id and testimony_id in testimonies_obj:
                        testimony = testimonies_obj.get(testimony_id)
                    elif isinstance(testimonies_obj, list):
                        for t in testimonies_obj:
                            if t.get("id") == testimony_id or (witness_id and t.get("witness_id") == witness_id):
                                testimony = t
                                break
                    else:
                        if isinstance(testimonies_obj, dict) and witness_id and testimonies_obj.get("witness_id") == witness_id:
                            testimony = testimonies_obj

                    all_statements = [s.get("id") for s in (testimony or {}).get("statements", [])]
                    seen = {c.get("target_statement_id") for c in trial_state.player_choices if c.get("target_statement_id")}
                    remaining = [s for s in all_statements if s not in seen]

                    if remaining:
                        # If there are remaining statements, return to CROSS_EXAMINATION by default
                        print("Back to cross-examination.")
                        next_phase_id = cross_phase_id or trial_state.next_phase_id(current_phase_id)
                    else:
                        # no remaining statements: proceed to judge reaction
                        judge_phase_id = None
                        for pid, p in trial_state.phases.items():
                            if p.get("type") == "JUDGE_REACTION":
                                judge_phase_id = pid
                                break
                        next_phase_id = judge_phase_id or next_phase_id or trial_state.next_phase_id(current_phase_id)

                    break
                print("Please choose 1 or 2.")

        elif phase_type == "FINAL_DEFENSE":
            # Compile prior choices and let the defense present a closing argument
            print("\nFinal Defense: craft your closing argument based on the case and choices made.")
            log_dialogue(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                speaker="Judge",
                text="Final Defense, craft your closing argument based on the case and choices made.",
                source="cli",
            )
            prior_lines = []
            for i, c in enumerate(trial_state.player_choices, start=1):
                arg = c.get("presented_argument") or c.get("argument")
                prior_lines.append(f"{i}. strategy={c.get('strategy')} target={c.get('target_statement_id')} arg={arg}")

            summary_context = "\n".join(prior_lines) or bundle.get("case", {}).get("summary", "")

            # run candidate generation for closing arguments
            retrieved = retriever.similarity_search(summary_context, k=retrieval_k)
            context = TrialContext(
                case_id=bundle["case"]["id"],
                case_title=bundle["case"]["title"],
                summary=bundle["case"]["summary"],
                current_phase=current_phase_id,
                player_action=f"Closing argument request. Prior choices:\n{summary_context}",
            )
            prompt = build_prompt(context=context, adaptation=adaptation, retrieved=retrieved)
            candidates = generate_candidates(
                bundle=bundle,
                adaptation=adaptation,
                k=k,
                prompt=prompt,
                use_ollama=use_ollama,
                ollama_model=ollama_model,
            )

            verified = [(cand, verify_candidate(bundle, cand, retrieved=retrieved)) for cand in candidates]
            player_choices = print_player_choices(verified)
            log_argument_options(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                options=[{"index": index, "text": re.sub(r'^\s*\[.*?\]\s*', '', candidate.argument), "intent": candidate.strategy } for index, candidate in enumerate(player_choices, start=1)],
                source="cli",
            )
            selected_candidate = choose_candidate(player_choices)

            if selected_candidate is not None:
                selected_verdict = next((verdict for cand, verdict in verified if cand.candidate_id == selected_candidate.candidate_id), None)
                if selected_verdict is not None:
                    # persist final defense as a player choice
                    trial_state.record_choice(selected_candidate, selected_verdict)
                    # attempt polishing the final defense
                    final_text = selected_candidate.argument
                    try:
                        import importlib
                        mod = importlib.import_module("project.generation.ollama_client")
                        ollama_generate_json = getattr(mod, "ollama_generate_json", None)
                    except Exception:
                        ollama_generate_json = None

                    if ollama_generate_json is not None:
                        try:
                            llm_out = ollama_generate_json(prompt=(
                                f"Polish the following closing argument to be concise, persuasive, and natural: {final_text}\n"
                                "Return a JSON array with one object containing the field 'argument' whose value is the polished line."
                            ), model=ollama_model, temperature=adaptation.temperature)
                            if isinstance(llm_out, list) and llm_out:
                                first = llm_out[0]
                                if isinstance(first, dict):
                                    final_text = first.get("argument") or first.get("text")
                                elif isinstance(first, str):
                                    final_text = first
                            elif isinstance(llm_out, dict):
                                final_text = llm_out.get("argument") or llm_out.get("text")
                            elif isinstance(llm_out, str):
                                final_text = llm_out
                        except Exception as e:
                            print("[debug] polishing final defense failed:", e)

                    print("\nFinal defense presented:")
                    log_dialogue(
                        repo_root / "project" / "logs" / "runtime.jsonl",
                        case_id=case_id,
                        speaker="Player",
                        text=final_text,
                        source="cli",
                    )
                    print(final_text)

            next_phase_id = trial_state.next_phase_id(current_phase_id)

        elif phase_type == "VERDICT":
            # Compute verdict based on case conditions and player's proven contradictions
            conditions = bundle.get("case", {}).get("conditions", {}) or {}
            required_contradictions = set(conditions.get("required_contradictions", []))

            # collect successful contradicted statement ids from player choices
            proven = {c.get("target_statement_id") for c in trial_state.player_choices if c.get("verdict_valid")}

            # decision rule: if required_contradictions are all proven, the defense succeeds -> NOT GUILTY
            if required_contradictions and required_contradictions.issubset(proven):
                decision = "NOT GUILTY"
                reason = f"Required contradictions proven: {sorted(list(required_contradictions))}"
            else:
                decision = "GUILTY"
                missing = sorted(list(required_contradictions - proven)) if required_contradictions else []
                reason = f"Missing required contradictions: {missing}" if required_contradictions else "No exculpatory contradictions were proven."

            judge = bundle.get("judge", {})
            judge_name = judge.get("name", "Judge")
            print(f"\nJudge {judge_name}: THE COURT FINDS THE DEFENDANT {decision}.")
            log_dialogue(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                speaker="Judge",
                text=f"THE COURT FINDS THE DEFENDANT {decision}.",
                source="cli_verdict",
            )
            print(f"Reason: {reason}")
            log_dialogue(
                repo_root / "project" / "logs" / "runtime.jsonl",
                case_id=case_id,
                speaker="Judge",
                text=f"Reason: {reason}",
                source="cli_verdict_reason",
            )

            # persist verdict into trial_state and logs for replay
            try:
                trial_state.final_verdict = {"decision": decision, "reason": reason}
            except Exception:
                pass

            try:
                append_log(repo_root / "project" / "logs" / "runtime.jsonl", {"event": "verdict", "case_id": bundle.get("case", {}).get("id"), "decision": decision, "reason": reason})
            except Exception:
                pass

            print("Reached VERDICT. Ending trial loop.")
            break

        else:
            print(f"Phase type '{phase_type}' not handled; advancing.")
            next_phase_id = trial_state.next_phase_id(current_phase_id)

        # default progression if contradiction didn't set an explicit next_phase
        current_phase_id = next_phase_id

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Courtroom AI core pipeline demo")
    parser.add_argument("--case-id", default="case_001")
    parser.add_argument("--query", default="Challenge statement stmt_3 with evidence")
    parser.add_argument("--tone", default="neutral", choices=["friendly", "neutral", "aggressive", "informative"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--use-chroma", action="store_true")
    parser.add_argument("--no-ollama", dest="use_ollama", action="store_false", help="Disable Ollama; use templates instead")
    parser.set_defaults(use_ollama=True)
    parser.add_argument("--ollama-model", default="llama3:8b", help="Ollama model name to use (e.g. llama3:8b)")
    parser.add_argument("--hint-level", type=float, default=0.9, help="Adaptation hint level (0-1) controlling NPC reinforcement)")
    parser.add_argument("--force-reindex", action="store_true", help="Force reindexing of the Chroma collection for the case")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    run_pipeline(
        repo_root=repo_root,
        case_id=args.case_id,
        query=args.query,
        tone=args.tone,
        k=args.k,
        retrieval_k=args.retrieval_k,
        use_chroma=args.use_chroma,
        use_ollama=args.use_ollama,
        ollama_model=args.ollama_model,
        hint_level=args.hint_level,
        force_reindex=args.force_reindex,
    )


if __name__ == "__main__":
    main()
