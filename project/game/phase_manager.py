# project/game/phase_manager.py
from __future__ import annotations
from abc import ABC, abstractmethod
from project.ui.cli_demo import print_player_choices, choose_candidate
from project.generation.candidate_generator import generate_candidates
from project.generation.prompt_builder import build_prompt

class TrialPhase(ABC):
    def __init__(self, phase_id: str, phase_data: dict, engine):
        self.phase_id = phase_id
        self.phase_data = phase_data
        self.engine = engine

    @abstractmethod
    def execute(self) -> str | None:
        pass


class IntroPhase(TrialPhase):
    def execute(self) -> str | None:
        case = self.engine.bundle.get("case", {})
        print(f"\n[SCENE FOCUS: {self.phase_data.get('scene', 'courtroom_opening').upper()}]")
        print(f"-> {case.get('summary', '')}")
        input("\nPress Enter to continue to the testimony...")
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
        print(f"\n=== TESTIMONY PHASE: {actual_witness.upper()} ===")
        for stmt in testimony.get("statements", []):
            print(f"  [{stmt.get('id')}]: \"{stmt.get('text')}\"")
            
        input("\nPress Enter to proceed to Cross-Examination...")
        return self.engine.trial_state.next_phase_id(self.phase_id)


class CrossExaminationPhase(TrialPhase):
    def execute(self) -> str | None:
        witness_id = self.phase_data.get("witness_id") or "witness_cashier"
        testimonies_dict = self.engine.bundle.get("testimonies", {})
        
        # 1. Localizar o depoimento da testemunha atual
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

        # project/game/phase_manager.py - Dentro de CrossExaminationPhase.execute()
        
        print(f"\n=== CROSS-EXAMINATION: {witness_id.upper()} ===")

        for idx, stmt in enumerate(statements):
            # Este loop controla se o jogador quer continuar a interagir com a MESMA frase
            while True:
                print(f"\n--------------------------------------------------")
                print(f"Statement [{idx + 1}]: \"{stmt.get('text')}\"")
                print(f"--------------------------------------------------")
                
                print(f">> Select your action for this statement:")
                print(" [1] Press Witness (Ask for more details)")
                print(" [2] Brainstorm Strategy Lines (Call LLM Team)")
                print(" [3] Present Evidence (Contradict)")
                print(" [Enter] Move to next statement")

                action_choice = input("Option: ").strip()

                # --- OPÇÃO 1: PRESS WITNESS ---
                if action_choice == "1":
                    if stmt.get("can_press"):
                        print(f"\n[DEFENSE ATTORNEY]: Hold it!")
        
                        current_witness_id = testimony.get("witness_id")
                        witness_state = self.engine.trial_state.witness_states.get(current_witness_id)
        
                        # Se por algum motivo o stress inicial estiver alto, vamos mitigá-lo para frases normais
                        stress_level = witness_state.stress if witness_state else 0
                        witness_name = witness_state.name if witness_state else "Kip Hunter"

                        # REGRA DE JOGO: Só damos 1 de dano no Press, por isso ela não deve pinar de stress logo aqui
                        if witness_state:
                            witness_state.apply_damage(1)
                            # Atualiza a variável local para refletir o estado atualizado
                            stress_level = witness_state.stress
        
                        # Pega na resposta estática do teu JSON (ex: "He's always been a nice guy...")
                        press_msg = stmt.get("press_response")

                        print(f"--- DEBUG: Stress da testemunha é {stress_level} ---")
                        
                        # Se a testemunha ainda tem pouco stress (ex: menos de 4), não a deixes entrar em pânico!
                        if stress_level < 4:
                            print(f"\n[{witness_name} (CALM)]: \"{press_msg}\"")
                        else:
                            # O gerador dinâmico do LLM só entra em ação se ela já estiver sob forte pressão acumulada
                            dynamic_response = self.engine.dialogue_generator.generate_press_response(current_witness_id, stress_level)
                            print(f"\n{dynamic_response}")
                            print(f"[{witness_name}]: \"{press_msg}\"")
                    else:
                        print(f"\n[DEFENSE ATTORNEY]: You press the statement, but the witness stands firm.")
        
                    input("\nPress enter to return to the statement options...")
                # --- OPÇÃO 2: BRAINSTORM STRATEGY LINES (O TEU LLM) ---
                elif action_choice == "2":
                    print(f"\n[Thinking...] Consulting your legal team about this specific statement...")
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
                        for c_idx, cand in enumerate(verified_candidates):
                            print(f"  [{c_idx + 1}] ({cand.strategy.upper()}): {cand.argument}")
            
                        arg_choice = input("\nChoose an argument strategy: ").strip()
                        selected_idx = int(arg_choice) - 1 if arg_choice.isdigit() else 0
                        if 0 <= selected_idx < len(verified_candidates):
                            chosen_candidate = verified_candidates[selected_idx]
                        else:
                            chosen_candidate = verified_candidates[0]
                
                        print(f"\n[DEFENSE ATTORNEY]: {chosen_candidate.argument}")
                        
                        # Criamos o veredito esperado pelo sistema de reações
                        from project.common.types import VerifierResult
                        is_valid_bool = VerifierResult(valid=True, reason="ok")

                        # Passamos os parâmetros corretos exigidos pelo módulo narrative
                        npc_reactions = self.engine.reaction_generator.generate_reactions(
                            chosen_candidate,   # candidate
                            is_valid_bool,      # verdict_valid (True/False)
                            "ARGUMENTATION"     # phase_type 
                        )
                        
                        print("\n=== REACTIONS ON THE TRIAL ===")
                        for rx in npc_reactions:
                            print(f"[{rx.npc_name} ({rx.mood.upper()})]: {rx.text}")

                        current_witness_id = testimony.get("witness_id")
                        if current_witness_id in self.engine.trial_state.witness_states:
                            self.engine.trial_state.witness_states[current_witness_id].apply_damage(3)
                        
                        input("\nPress enter to advance with this strategic line...")
                        return self.engine.trial_state.next_phase_id(self.phase_id)
                    else:
                        print("\n[DEFENSE ATTORNEY]: (None of my tactical arguments feel stable enough to say out loud right now.)")
                    input("\nPress enter to return to the statement options...")

                # --- OPÇÃO 3: PRESENT EVIDENCE (CONTRADICT) ---
                elif action_choice == "3":
                    print("\nAvailable Evidence Inventory:")
                    evidence_list = self.engine.bundle.get("evidence", [])
                    if isinstance(evidence_list, dict):
                        evidence_list = list(evidence_list.values())

                    for e_idx, ev in enumerate(evidence_list):
                        print(f"  [{e_idx + 1}] {ev.get('id')}: {ev.get('name')}")
                    
                    ev_choice = input("Select evidence number to present: ").strip()
                    if ev_choice.isdigit():
                        ev_idx = int(ev_choice) - 1
                        if 0 <= ev_idx < len(evidence_list):
                            selected_evidence = evidence_list[ev_idx]
                            evidence_id = selected_evidence.get("id")
                            stmt_id = stmt.get("id")
                            
                            print(f"\n[Processing Action]: Presenting {evidence_id} against {stmt_id}...")
                            
                            can_contradict_list = selected_evidence.get("can_contradict", [])
                            if isinstance(can_contradict_list, str):
                                can_contradict_list = [can_contradict_list]
                            
                            is_valid_contradiction = stmt_id in can_contradict_list

                            if is_valid_contradiction:
                                print(f"\n💥 OBJECTION! That's a direct contradiction!")
                                print(f"[JUDGE]: Sustained! The witness's statement cannot be true given the '{selected_evidence.get('name')}'!")
        
                                fact_id = f"fact_{stmt_id}" 
                                if stmt_id == "stmt_3": fact_id = "fact_001"
                                elif stmt_id == "stmt_5": fact_id = "fact_002"

                                self.engine.action_resolver.discovery_engine.reveal_fact(fact_id)
                                self.engine.trial_state.contradictions_found.append(stmt_id)
        
                                print(f"\n[ANALYSIS]: Based on this contradiction, the defense proved that the info in {stmt_id} is false.")
                                print(f"Trial Verdict Progress: {self.engine.trial_state.verdict_progress * 100:.1f}%")
        
                                current_witness_id = testimony.get("witness_id")
                                if current_witness_id in self.engine.trial_state.witness_states:
                                    self.engine.trial_state.witness_states[current_witness_id].apply_damage(4)
                                    print(f"[{self.engine.trial_state.witness_states[current_witness_id].name} STRESS]: {self.engine.trial_state.witness_states[current_witness_id].stress}/10")

                                input("\nPress enter to advance with this advantage...")
                                return self.engine.trial_state.next_phase_id(self.phase_id)
                            else:
                                print(f"\n[JUDGE]: Overruled! That evidence doesn't seem to contradict what the witness just said.")
                                input("\nPress enter to return to the statement options...")

                # --- OPÇÃO ENTER: SAIR DESTE STATEMENT E IR PARA O SEGUINTE ---
                elif action_choice == "":
                    break # Quebra o while True interno e passa para o próximo statement do loop for

        return self.engine.trial_state.next_phase_id(self.phase_id)

class PhaseManager:
    def __init__(self, engine, retriever, trial_state, adaptation, ollama_model: str):
        self.engine = engine
        self._registry = {
            "INTRO": IntroPhase,
            "TESTIMONY": TestimonyPhase,
            "CROSS_EXAMINATION": CrossExaminationPhase
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