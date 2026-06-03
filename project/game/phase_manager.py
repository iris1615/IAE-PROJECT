# project/game/phase_manager.py
from __future__ import annotations
from abc import ABC, abstractmethod
from types import SimpleNamespace
from project.ui.cli_demo import print_player_choices, choose_candidate
from project.generation.candidate_generator import generate_candidates
from project.generation.prompt_builder import build_prompt
from project.generation.symbolic_verifier import verify_candidate

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

        print(f"\n=== CROSS-EXAMINATION: {witness_id.upper()} ===")

        # 2. Correr a pipeline dinamicamente statement por statement
        for idx, stmt in enumerate(statements):
            print(f"\n--------------------------------------------------")
            print(f"Statement [{idx + 1}]: \"{stmt.get('text')}\"")
            print(f"--------------------------------------------------")
            
            # Preparar o contexto para o teu build_prompt antigo
            # (Podes usar o teu retriever local ou Chroma para obter os chunks relevantes)
            retrieved_chunks = self.engine.retriever.similarity_search(stmt.get('text'), k=3)
            
            # Construir o prompt robusto que já tinhas desenvolvido
            from project.common.types import TrialContext
            context_obj = TrialContext(
                case_id=self.engine.bundle["case"]["id"],
                case_title=self.engine.bundle["case"].get("title", "Case"),
                summary=self.engine.bundle["case"].get("summary", ""),
                current_phase="CROSS_EXAMINATION",
                player_action=f"Reviewing statement: {stmt.get('text')}"
            )
            
            # 1. Grab fields safely using getattr with empty list fallbacks
            # Check if your TrialState uses attributes instead of methods, or fallback to []
            known_truths = []
            if hasattr(self.engine.trial_state, "known_truths"):
                known_truths = self.engine.trial_state.known_truths
            elif hasattr(self.engine.trial_state, "get_known_truths"):
                known_truths = self.engine.trial_state.get_known_truths()

            proven_steps = []
            if hasattr(self.engine.trial_state, "proven_steps"):
                proven_steps = self.engine.trial_state.proven_steps
            elif hasattr(self.engine.trial_state, "get_proven_steps"):
                proven_steps = self.engine.trial_state.get_proven_steps()

            prompt = build_prompt(
                context=context_obj,
                adaptation=self.engine.adaptation_config,  
                retrieved=retrieved_chunks,
                known_truths=known_truths,  # Safe list variable
                proven_steps=proven_steps   # Safe list variable
            )
            
            # 1. Gerar os 5 candidatos iniciais (k=5)
            candidates = generate_candidates(
                bundle=self.engine.bundle,
                adaptation=self.engine.adaptation_config,
                k=5,  # Voltamos ao teu plano original de 5!
                prompt=prompt,
                use_ollama=True,
                ollama_model="llama3:8b"
            )

            # 2. Filtrar os candidatos usando o teu Verifier antigo
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

                # --- NOVA VERIFICAÇÃO ROBUSTA ---
                # Se validation_result for um objeto, tentamos ler .is_valid ou .success. 
                # Como fallback supremo, se a mensagem for "ok", o argumento é válido!
                is_ok = False
                if isinstance(validation_result, bool):
                    is_ok = validation_result
                else:
                    is_ok = (
                        getattr(validation_result, "is_valid", False) or 
                        getattr(validation_result, "success", False) or 
                        getattr(validation_result, "reason", "").lower() == "ok"
                    )

                if is_ok:
                    verified_candidates.append(cand_obj)
                else:
                    # Imprime o motivo real do descarte para sabermos o que a IA falhou
                    reason_msg = getattr(validation_result, "reason", str(validation_result))
                    print(f"[debug-verifier-failed] Strategy '{cand_obj.strategy}': {reason_msg}")
                    
            # 3. Mostrar ao jogador apenas os argumentos validados pela "equipa jurídica" (Pipeline)
            if verified_candidates:
                print(f"\nSelect your Strategy Line (Verified Arguments):")
                for c_idx, cand in enumerate(verified_candidates):
                    print(f"  [{c_idx + 1}] ({cand.strategy.upper()}): {cand.argument}")
    
                # Validação da escolha do jogador
                arg_choice = input("\nChoose an argument strategy: ").strip()
                selected_idx = int(arg_choice) - 1 if arg_choice.isdigit() else 0
                if not (0 <= selected_idx < len(verified_candidates)):
                    selected_idx = 0
        
                    chosen_candidate = verified_candidates[selected_idx]
                    print(f"\n[DEFENSE ATTORNEY]: {chosen_candidate.argument}")
                    print(f"[PROSECUTOR]: Objection! The witness is clearly recounting what they saw!")
                else:
                    # Fallback caso o número digitado seja inválido
                    chosen_candidate = verified_candidates[0]
                    print(f"\n[DEFENSE ATTORNEY]: {chosen_candidate.argument}")
                    print(f"[PROSECUTOR]: Objection! The witness is clearly recounting what they saw!")
            else:
                # Fallback caso o modelo tenha falhado todas as validações ou o verifier tenha sido implacável
                print("\n[DEFENSE ATTORNEY]: (Thinking... None of my arguments seem structurally sound right now.)")

            # 3. Dar a escolha orgânica de jogabilidade em Inglês
            print(f"\n>> Do you want to challenge this statement with evidence?")
            print(" [1] Present Evidence")
            print(" [Enter] Move to the next statement")
            
            choice = input("Select an option: ").strip()
            # presents evidence to contradict statement
            if choice == "1":
                # Mostrar o Inventário de Provas
                print("\nAvailable Evidence Inventory:")
                evidence_list = self.engine.bundle.get("evidence", [])
                
                # Suporte caso o bundle traga a evidência como dicionário mapeado por ID
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
                        
                        stmt_id = stmt.get("id")  # ex: "stmt_5"
                        print(f"\n[Processing Action]: Presenting {evidence_id} against {stmt_id}...")
                        
                        # --- NOVA VALIDAÇÃO INVERTIDA (A prova dita o que contradiz!) ---
                        # 1. Buscar a lista de statements que esta prova consegue derrubar
                        can_contradict_list = selected_evidence.get("can_contradict", [])
                        
                        # Suportar tanto se for uma String única quanto uma Lista de Strings
                        if isinstance(can_contradict_list, str):
                            can_contradict_list = [can_contradict_list]
                        
                        # 2. Verificar se o statement atual está na lista de alvos da prova
                        is_valid_contradiction = stmt_id in can_contradict_list

                        # 3. Dar o veredito do Juiz baseado nos Schemas reais do teu caso
                        if is_valid_contradiction:
                            print(f"\n💥 OBJECTION! That's a direct contradiction!")
                            print(f"[JUDGE]: Sustained! The witness's statement cannot be true given the '{selected_evidence.get('name')}'.")
                            
                            # Registar o progresso com sucesso no teu motor de estados
                            if hasattr(self.engine.trial_state, "register_contradiction"):
                                self.engine.trial_state.register_contradiction(stmt_id, evidence_id)
                            
                            # Interrompe o testemunho atual e avança vitorioso para a próxima fase!
                            return self.engine.trial_state.next_phase_id(self.phase_id)
                        else:
                            print(f"\n[PENALTY]: The Judge bangs the gavel! There's no contradition there!.")
                            # Mensagem opcional de debug em inglês para te ajudar no desenvolvimento
                            # print(f"[Debug] Evidence '{evidence_id}' targets {can_contradict_list}, but you attacked '{stmt_id}'.")
                            
                            if hasattr(self.engine.trial_state, "apply_penalty"):
                                self.engine.trial_state.apply_penalty()
                            
        # Se percorreu todos os statements e não quebrou nenhum, segue para a próxima fase
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