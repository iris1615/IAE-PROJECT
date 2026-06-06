# project/game/phase_manager.py
from __future__ import annotations
from abc import ABC, abstractmethod
from types import SimpleNamespace
from project.generation.candidate_generator import generate_candidates
from project.generation.prompt_builder import build_prompt
from project.generation.symbolic_verifier import verify_candidate
from project.common.log_events import log_dialogue, log_argument_options, log_evidence, log_statement, read_input_events, reset_log_events

class TrialPhase(ABC):
    def __init__(self, phase_id: str, phase_data: dict, engine):
        self.phase_id = phase_id
        self.phase_data = phase_data
        self.engine = engine
        self.cli_flagg = False  # Set to True to enable CLI input, False to read from logs (for Streamlit integration)

    @abstractmethod
    def execute(self) -> str | None:
        pass
    
    def streamlit_input(self):
        value = ""
        while not value:
            value = read_input_events(self.engine.repo_root / "logs" / "input.jsonl", max_events=1)
            if value:
                reset_log_events(self.engine.repo_root / "logs" / "input.jsonl")
                return str(value).strip().lower()



class IntroPhase(TrialPhase):
    def execute(self) -> str | None:
        case = self.engine.bundle.get("case", {})
        print(f"\n[SCENE FOCUS: {self.phase_data.get('scene', 'courtroom_opening').upper()}]")
        print(f"-> {case.get('summary', '')}")

        log_dialogue(
            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
            speaker="Narrator",
            text=case.get('summary', ''),
            source="phase_manager.IntroPhase"
        )

        if self.cli_flagg:
            input("\nPress Enter to continue to the testimony...")
        else:
            log_argument_options(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                source="phase_manager.IntroPhase"
            )
            self.streamlit_input()
        return self.engine.trial_state.next_phase_id(self.phase_id)


class TestimonyPhase(TrialPhase):
    def execute(self) -> str | None:
        testimony_id = self.phase_data.get("testimony_id")
        witness_id = self.phase_data.get("witness_id")
        
        testimonies_dict = self.engine.bundle.get("testimonies", {})
        testimony = {}
        
        # Iterar corretamente pelos valores do dicionário de depoimentos
        for t in testimonies_dict.values():
            if t.get("id") == testimony_id or t.get("witness_id") == witness_id:
                testimony = t
                break

        if not testimony and testimonies_dict:
            testimony = list(testimonies_dict.values())[0]

        actual_witness = testimony.get("witness_id", witness_id)
        witness_name = testimony.get("witness_name", "Unknown Witness")
        print(f"\n=== TESTIMONY PHASE: {actual_witness.upper()} ===")
        for stmt in testimony.get("statements", []):
            print(f"  [{stmt.get('id')}]: \"{stmt.get('text')}\"")
            
            log_dialogue(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                speaker= witness_name,
                text=stmt.get("text", ""),
                source="phase_manager.TestimonyPhase"
            )
            
        if self.cli_flagg:
            input("\nPress Enter to proceed to Cross-Examination...")
        else:
            log_argument_options(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                source="phase_manager.TestimonyPhase"
            )
            self.streamlit_input()
        return self.engine.trial_state.next_phase_id(self.phase_id)


class CrossExaminationPhase(TrialPhase):
    def execute(self) -> str | None:
        witness_id = self.phase_data.get("witness_id") or "witness_cashier"
        testimonies_dict = self.engine.bundle.get("testimonies", {})
        
        testimony = None
        for t in testimonies_dict.values():
            if t.get("witness_id") == witness_id:
                testimony = t
                break
                
        if not testimony and testimonies_dict:
            testimony = list(testimonies_dict.values())[0]
            
        statements = (testimony or {}).get("statements", [])
        if not statements:
            print(f"\n[System] No statements found for cross-examination of {witness_id}.")
            return self.engine.trial_state.next_phase_id(self.phase_id)
        
        #garantee that the stress levels start at zero
        current_witness_id = testimony.get("witness_id")
        witness_state = self.engine.trial_state.witness_states.get(current_witness_id)
        if witness_state and not hasattr(witness_state, "_initialized_this_phase"):
            witness_state.stress = 0 
            witness_state._initialized_this_phase = True
        
        print(f"\n=== CROSS-EXAMINATION: {witness_id.upper()} ===")

        current_idx = 0
        total_statements = len(statements)

        while True:
            stmt = statements[current_idx]
            
            print(f"\n--------------------------------------------------")
            print(f"Statement [{current_idx + 1}/{total_statements}]: \"{stmt.get('text')}\"")
            print(f"--------------------------------------------------")

            log_statement(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                statement_id=stmt.get("id", f"stmt_{current_idx}"),
                text=stmt.get("text", ""),
                source="phase_manager.CrossExaminationPhase"
            )
            
            print(f">> Select your action for this statement:")
            print(" [1] Press Witness (Ask for more details)")
            print(" [2] Brainstorm Strategy Lines (Think in arguments)")
            print(" [3] Present Evidence (Contradict)")
            print(" [A] Previous Statement")
            print(" [D] Next Statement")
            print(" [Q] Quit Cross-Examination (Advance Phase)")
            print(" [Enter] Quick-move to Next Statement")

            log_argument_options(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                options=[
                    {"intent": "Press Witness", "text": "Ask the witness to elaborate or clarify this statement."},
                    {"intent": "Brainstorm Strategy Lines", "text": "Think of possible arguments or strategies related to this statement."},
                    {"intent": "Present Evidence", "text": "Use an item from your evidence inventory to try to contradict this statement."},
                    {"intent": "Previous Statement", "text": "Go back to the previous statement in the testimony."},
                    {"intent": "Next Statement", "text": "Advance to the next statement in the testimony."},
                    {"intent": "Quit Cross-Examination", "text": "End the cross-examination phase and move on."}
                ],
                source="phase_manager.CrossExaminationPhase"
            )
            if self.cli_flagg:
                action_choice = input("Option: ").strip().lower()
            else:
                action_choice = self.streamlit_input()

            if action_choice == "a" or action_choice == "4":
                current_idx = (current_idx - 1) % total_statements
                continue
            elif action_choice == "d" or action_choice == "5":
                current_idx = (current_idx + 1) % total_statements
                continue
            elif action_choice == "q" or action_choice == "6":
                break

            # --- PRESS WITNESS ---
            elif action_choice == "1":
                if stmt.get("can_press"):
                    print(f"\n[DEFENSE ATTORNEY]: Hold it!")
                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Connor Rose[You]",
                        text="Hold it!",
                        source="phase_manager.CrossExaminationPhase"
                    )
                    
                    # Generates dynamic interrogation when pressing
                    defense_press_line = "(Wait, something doesn't add up here...)"
                    if self.engine.use_ollama:
                        try:
                            import ollama
                            case_title = self.engine.bundle.get("case", {}).get("title", "Case")
                            stmt_text = stmt.get("text", "")
                            
                            press_prompt = (
                                f"You are the defense attorney in an Ace Attorney game style.\n"
                                f"Case: {case_title}\n"
                                f"The witness just stated: \"{stmt_text}\"\n"
                                f"TASK:\n"
                                f"Write a single sharp, inquisitive, or combative sentence that the defense attorney "
                                f"says out loud to pressure the witness about this specific statement. "
                                f"Keep it brief (max 1-2 sentences), professional yet dramatic. Do NOT include any meta-text, names or brackets."
                            )
                            
                            resp = ollama.chat(model=self.engine.ollama_model, messages=[{"role": "user", "content": press_prompt}])
                            defense_press_line = resp['message']['content'].strip().replace('"', '')
                        except Exception:
                            defense_press_line = f"Are you absolutely sure about that? Your account regarding '{stmt_text}' seems highly questionable!"
                    
                    # Imprime a fala gerada para o jogador
                    print(f"[DEFENSE ATTORNEY]: \"{defense_press_line}\"")
                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Connor Rose[You]",
                        text=defense_press_line,
                        source="phase_manager.CrossExaminationPhase"
                    )
                    print(f"--------------------------------------------------")

                    current_witness_id = testimony.get("witness_id")
                    witness_state = self.engine.trial_state.witness_states.get(current_witness_id)
    
                    if witness_state:
                        witness_state.apply_damage(1)
                        stress_level = witness_state.stress
                        witness_name = witness_state.name
                    else:
                        stress_level = 0
                        witness_name = "Witness"

                    print(f"--- DEBUG: Witness Stress level {stress_level} ---")
                    
                    # Accumulated stress reaction
                    if stress_level < 4:
                        press_msg = stmt.get("press_response", "...")
                        print(f"\n[{witness_name} (CALM)]: \"{press_msg}\"")
                        log_dialogue(
                            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                            speaker=f"{witness_name} (CALM)",
                            text=press_msg,
                            source="phase_manager.CrossExaminationPhase"
                        )
                    else:
                        dynamic_response = self.engine.dialogue_generator.generate_press_response(current_witness_id, stress_level)
                        print(f"\n{dynamic_response}")
                        log_dialogue(
                            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                            speaker=f"{witness_name} (STRESSED)",
                            text=dynamic_response,
                            source="phase_manager.CrossExaminationPhase"
                        )
                else:
                    print(f"\n[DEFENSE ATTORNEY]: You press the statement, but the witness stands firm.")
                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Connor Rose[You]",
                        text="You press the statement, but the witness stands firm.",
                        source="phase_manager.CrossExaminationPhase"
                    )
    
                
                if self.cli_flagg:
                    input("\nPress enter to return to the statement options...")
                else:
                    log_argument_options(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                        source="phase_manager.TestimonyPhase"
                    )
                    self.streamlit_input()
                
            # --- BRAINSTORM STRATEGY LINES (LLM) ---
            elif action_choice == "2":
                print(f"\n[Thinking...] Consulting your legal team about this specific statement...")
                log_dialogue(
                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                    speaker="Connor Rose[You]",
                    text="[Thinking...] Consulting your legal team about this specific statement... (PLEASE WAIT...)",
                    source="phase_manager.CrossExaminationPhase.BrainstormingStart"
                )
                retrieved_chunks = self.engine.retriever.similarity_search(stmt.get('text'), k=3)
                
                from project.common.types import TrialContext
                context_obj = TrialContext(
                    case_id=self.engine.bundle["case"]["id"],
                    case_title=self.engine.bundle["case"].get("title", "Case"),
                    summary=self.engine.bundle["case"].get("summary", ""),
                    current_phase="CROSS_EXAMINATION",
                    player_action=f"Reviewing statement: {stmt.get('text')}"
                )
                
                known_truths = self.engine.trial_state.known_truths if hasattr(self.engine.trial_state, "known_truths") else []
                proven_steps = self.engine.trial_state.proven_steps if hasattr(self.engine.trial_state, "proven_steps") else []

                prompt = build_prompt(
                    context=context_obj,
                    adaptation=self.engine.adaptation_config,
                    retrieved=retrieved_chunks,
                    known_truths=known_truths,
                    proven_steps=proven_steps
                )
                
                candidates = generate_candidates(
                    bundle=self.engine.bundle,
                    adaptation=self.engine.adaptation_config,
                    k=5,
                    prompt=prompt,
                    use_ollama=True,
                    ollama_model="llama3:8b"
                )

                verified_candidates = []
                for cand in candidates:
                    if isinstance(cand, dict):
                        cand_obj = SimpleNamespace(**cand)
                    else:
                        cand_obj = cand

                    if not hasattr(cand_obj, "argument") and hasattr(cand_obj, "text"):
                        cand_obj.argument = cand_obj.text
                    if not hasattr(cand_obj, "strategy"):
                        cand_obj.strategy = "logic"

                    validation_result = verify_candidate(
                        bundle=self.engine.bundle,
                        candidate=cand_obj,
                        retrieved=retrieved_chunks,
                        current_statement_id=stmt.get("id")
                    )

                    is_ok = isinstance(validation_result, bool) and validation_result or (
                        getattr(validation_result, "is_valid", False) or 
                        getattr(validation_result, "success", False) or 
                        getattr(validation_result, "reason", "").lower() == "ok"
                    )

                    if is_ok:
                        verified_candidates.append(cand_obj)
                    else:
                        reason_msg = getattr(validation_result, "reason", str(validation_result))
                        print(f"[debug-verifier-failed] Strategy '{cand_obj.strategy}': {reason_msg}")

                if verified_candidates:
                    print(f"\nSelect your Strategy Line (Verified Arguments):")
                    options_list = []
                    for c_idx, cand in enumerate(verified_candidates):
                        print(f"  [{c_idx + 1}] ({cand.strategy.upper()}): {cand.argument}")
                        options_list.append({"intent": cand.strategy, "text": cand.argument})
                    log_argument_options(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        options=options_list,
                        source="phase_manager.CrossExaminationPhase.VerifiedCandidates"
                    )

                    if self.cli_flagg:
                        arg_choice = input("\nChoose an argument strategy: ").strip()
                    else:
                        arg_choice = self.streamlit_input()

                    selected_idx = int(arg_choice) - 1 if arg_choice.isdigit() else 0
                    if 0 <= selected_idx < len(verified_candidates):
                        chosen_candidate = verified_candidates[selected_idx]
                    else:
                        chosen_candidate = verified_candidates[0]
            
                    print(f"\n[DEFENSE ATTORNEY]: {chosen_candidate.argument}")
                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Connor Rose[You]",
                        text=chosen_candidate.argument,
                        source="phase_manager.CrossExaminationPhase.ChosenArgument"
                    )
                    
                    from project.common.types import VerifierResult
                    is_valid_bool = VerifierResult(valid=True, reason="ok")

                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Narrator",
                        text="The courtroom reacts to your argument choice... (PLEASE WAIT...)",
                        source="phase_manager.CrossExaminationPhase.ArgumentReaction"
                    )
                    npc_reactions = self.engine.reaction_generator.generate_reactions(
                        chosen_candidate,   
                        is_valid_bool,      
                        "ARGUMENTATION"     
                    )
                    
                    print("\n=== REACTIONS ON THE TRIAL ===")
                    for rx in npc_reactions:
                        print(f"[{rx.npc_name} ({rx.mood.upper()})]: {rx.text}")
                        log_dialogue(
                            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                            speaker=f"{rx.npc_name}",
                            text=rx.text,
                            source="phase_manager.CrossExaminationPhase.NPCReaction"
                        )

                    current_witness_id = testimony.get("witness_id")
                    
                else:
                    print("\n[DEFENSE ATTORNEY]: (None of my tactical arguments feel stable enough to say out loud right now.)")
                    log_dialogue(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        speaker="Connor Rose[You]",
                        text="(None of my tactical arguments feel stable enough to say out loud right now.)",
                        source="phase_manager.CrossExaminationPhase.NoValidArguments"
                    )
                
                if self.cli_flagg:
                    input("\nPress enter to return to the statement options...")
                else:
                    log_argument_options(
                        log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                        options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                        source="phase_manager.TestimonyPhase"
                    )
                    self.streamlit_input()

            # --- PRESENT EVIDENCE (CONTRADICT) ---
            elif action_choice == "3":
                print("\nAvailable Evidence Inventory:")
                evidence_list = self.engine.bundle.get("evidence", [])
                if isinstance(evidence_list, dict):
                    evidence_list = list(evidence_list.values())

                evidence_options = []
                for e_idx, ev in enumerate(evidence_list):
                    print(f"  [{e_idx + 1}] {ev.get('id')}: {ev.get('name')}")
                    evidence_options.append({"intent": "Present Evidence", "text": f"{ev.get('name')}"})
                log_argument_options(
                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                    options=evidence_options,
                    source="phase_manager.CrossExaminationPhase.EvidenceInventory"
                )
                
                if self.cli_flagg:
                    ev_choice = input("Select evidence number to present: ").strip()
                else:
                    ev_choice = self.streamlit_input()


                if ev_choice.isdigit():
                    ev_idx = int(ev_choice) - 1
                    if 0 <= ev_idx < len(evidence_list):
                        selected_evidence = evidence_list[ev_idx]
                        evidence_id = selected_evidence.get("id")
                        stmt_id = stmt.get("id")
                        
                        print(f"\n[Processing Action]: Presenting {evidence_id} against {stmt_id}...")
                        log_evidence(
                            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                            title=selected_evidence.get("name", "Unknown Evidence"),
                            description=selected_evidence.get("description", ""),
                            source="phase_manager.CrossExaminationPhase.PresentEvidence"
                        )
                        
                        can_contradict_list = selected_evidence.get("can_contradict", [])
                        if isinstance(can_contradict_list, str):
                            can_contradict_list = [can_contradict_list]
                        
                        is_valid_contradiction = stmt_id in can_contradict_list

                        if is_valid_contradiction:
                            print(f"\n💥 OBJECTION! That's a direct contradiction!")

                            log_dialogue(
                                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                speaker="Connor Rose[You]",
                                text=f"\n💥 OBJECTION! That's a direct contradiction!",
                                source="phase_manager.CrossExaminationPhase.ObjectionRaised"
                            )

                            print(f"[JUDGE]: Sustained! The witness's statement cannot be true given the '{selected_evidence.get('name')}'!")

                            log_dialogue(
                                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                speaker="Judge Judy",
                                text=f"Sustained! The witness's statement cannot be true given the '{selected_evidence.get('name')}'!",
                                source="phase_manager.CrossExaminationPhase.ContradictionSustained"
                            )

                            fact_id = f"fact_{stmt_id}" 
                            if stmt_id == "stmt_3": fact_id = "fact_001"
                            elif stmt_id == "stmt_5": fact_id = "fact_002"

                            self.engine.action_resolver.discovery_engine.reveal_fact(fact_id)
                            self.engine.trial_state.contradictions_found.append(stmt_id)
    
                            print(f"\n[ANALYSIS]: Based on this contradiction, the defense proved that the info in {stmt_id} is false.")
                            log_dialogue(
                                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                speaker="Narrator",
                                text=f"Based on this contradiction, the defense proved that the info in {stmt_id} is false.",
                                source="phase_manager.CrossExaminationPhase.ContradictionNarration"
                            )
                            print(f"Trial Verdict Progress: {self.engine.trial_state.verdict_progress * 100:.1f}%")
                            log_dialogue(
                                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                speaker="Narrator",
                                text=f"Trial Verdict Progress: {self.engine.trial_state.verdict_progress * 100:.1f}%",
                                source="phase_manager.CrossExaminationPhase.VerdictProgress"
                            )
    
                            current_witness_id = testimony.get("witness_id")
                            if current_witness_id in self.engine.trial_state.witness_states:
                                self.engine.trial_state.witness_states[current_witness_id].apply_damage(4)
                                print(f"[{self.engine.trial_state.witness_states[current_witness_id].name} STRESS]: {self.engine.trial_state.witness_states[current_witness_id].stress}/10")

                            
                            if self.cli_flagg:
                                input("\nPress enter to advance with this advantage...")
                            else:
                                log_argument_options(
                                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                    options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                                    source="phase_manager.TestimonyPhase"
                                )
                                self.streamlit_input()
                            return self.engine.trial_state.next_phase_id(self.phase_id)
                        else:
                            print(f"\n[JUDGE]: Overruled! That evidence doesn't seem to contradict what the witness just said.")
                            log_dialogue(
                                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                speaker="Judge Judy",
                                text=f"Overruled! That evidence doesn't seem to contradict what the witness just said.",
                                source="phase_manager.CrossExaminationPhase.ContradictionOverruled"
                            )
                                
                            if self.cli_flagg:
                                input("\nPress enter to return to the statement options...")
                            else:
                                log_argument_options(
                                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                                    options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                                    source="phase_manager.TestimonyPhase"
                                )
                                self.streamlit_input()

        return self.engine.trial_state.next_phase_id(self.phase_id)


class FinalDefensePhase(TrialPhase):
    def execute(self) -> str | None:
        print(f"\n=== FINAL DEFENSE: CLOSING ARGUMENT ===")
        print("[DEFENSE ATTORNEY]: Your Honor, based on all the evidence set out today...")
        log_dialogue(
            log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
            speaker="Connor Rose[You]",
            text="Your Honor, based on all the evidence set out today...",
            source="phase_manager.FinalDefensePhase.OpeningStatement"
        )
        
        discovered_fact_ids = self.engine.trial_state.discovered_facts
        facts_bundle = self.engine.bundle.get("truth", {}).get("facts", [])
        
        discovered_texts = []
        for f in facts_bundle:
            if f.get("id") in discovered_fact_ids:
                discovered_texts.append(f.get("truth"))
                
        # If we dont have access to the hidden truths then uses context till now.
        if not discovered_texts:
            discovered_texts = [
                "We actually have no idea of whats going on here..."
            ]

        # If ollama and we have the hidden facts
        if discovered_texts and self.engine.use_ollama:
            facts_str = "\n".join([f"- {text}" for text in discovered_texts])
            
            prompt = (
                f"You are the defense attorney delivering a final, dramatic closing argument in an Ace Attorney style.\n"
                f"The case is strictly about a defendant accused of trying to buy a Pastel de Nata with Monopoly money.\n\n"
                f"PROVEN FACTS IN THIS TRIAL (You MUST build your argument exclusively around these points):\n"
                f"{facts_str}\n\n"
                f"STRICT RULES:\n"
                f"1. Explain that the defendant is an innocent regular customer who had no idea the bill was fake.\n"
                f"2. Expose Shane Wallace (the person in line) as the true culprit who framed the defendant to get content for his crime podcast.\n"
                f"3. Mention how the Security Camera Footage broke the witnesses' lies wide open.\n"
                f"4. Do NOT invent unrelated crimes (absolutely NO murders, NO office windows, NO phone calls).\n"
                f"5. Keep it powerful, theatrical, and concise (max 3-4 paragraphs). Do not include any meta-text or markdown headers."
            )
            
            try:
                import ollama
                resp = ollama.chat(
                    model=self.engine.ollama_model, 
                    messages=[{"role": "user", "content": prompt}],
                    options={"temperature": 0.5}  # Temperatura mais baixa reduz a alucinação!
                )
                print(f"\n{resp['message']['content'].strip()}")
                log_dialogue(
                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                    speaker="Connor Rose[You]",
                    text=resp['message']['content'].strip(),
                    source="phase_manager.FinalDefensePhase.OllamaClosingArgument"
                )
            except Exception as e:
                print("\n[DEFENSE ATTORNEY]: The contradictions prove the absolute truth! The security footage clearly shows my client was framed by the very person standing behind him in line!")
                log_dialogue(
                    log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                    speaker="Connor Rose[You]",
                    text="The contradictions prove the absolute truth! The security footage clearly shows my client was framed by the very person standing behind him in line!",
                    source="phase_manager.FinalDefensePhase.DefaultClosingArgument"
                )
                    
        else:
            print("\n[DEFENSE ATTORNEY]: ...Unfortunately, the evidence gathered cannot fully counter the accusation.")
            log_dialogue(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                speaker="Connor Rose[You]",
                text="...Unfortunately, the evidence gathered cannot fully counter the accusation.",
                source="phase_manager.FinalDefensePhase.NoFactsClosingArgument"
            )

        if self.cli_flagg:
            input("\nPress Enter to hear the Judge Veredict...")
        else:
            log_argument_options(
                log_file= self.engine.repo_root / "logs" / "runtime.jsonl",
                options=[{"intent": "Continue", "text": "Click \"Present\" to return to the statement options..."}],
                source="phase_manager.TestimonyPhase"
            )
            self.streamlit_input()
        return self.engine.trial_state.next_phase_id(self.phase_id)


class PhaseManager:
    def __init__(self, engine, retriever, trial_state, adaptation, ollama_model: str):
        self.engine = engine
        self._registry = {
            "INTRO": IntroPhase,
            "TESTIMONY": TestimonyPhase,
            "CROSS_EXAMINATION": CrossExaminationPhase,
            "FINAL_DEFENSE": FinalDefensePhase
        }

    def execute_phase(self, phase_id: str) -> str | None:
        phase_data = self.engine.trial_state.phases.get(phase_id)
        if not phase_data:
            return None
        
        phase_type = phase_data.get("type")
        phase_class = self._registry.get(phase_type)
        if phase_class:
            return phase_class(phase_id, phase_data, self.engine).execute()
        return self.engine.trial_state.next_phase_id(phase_id)