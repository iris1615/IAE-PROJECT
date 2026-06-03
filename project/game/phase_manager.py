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
            

            candidates = generate_candidates(
                bundle=self.engine.bundle,
                adaptation=self.engine.adaptation_config,
                k=3,
                prompt=prompt,
                use_ollama=True,
                ollama_model="llama3:8b"
            )
            
            # Se a IA gerou argumentos, mostra o primeiro como a "fala/provocação" do advogado
            if candidates and len(candidates) > 0:
                print(f"\n[DEFENSE ATTORNEY]: {candidates[0].argument}")
                print(f"[PROSECUTOR]: Objection! The witness is clearly recounting what they saw!")
            else:
                print("\n[DEFENSE ATTORNEY]: (Analyzing this claim closely...)")

            # 3. Dar a escolha orgânica de jogabilidade em Inglês
            print(f"\n>> Do you want to challenge this statement with evidence?")
            print(" [1] Present Evidence")
            print(" [Enter] Move to the next statement")
            
            choice = input("Select an option: ").strip()
            
            if choice == "1":
                # Mostrar o Inventário
                print("\nAvailable Evidence Inventory:")
                evidence_list = self.engine.bundle.get("evidence", [])
                for e_idx, ev in enumerate(evidence_list):
                    print(f"  [{e_idx + 1}] {ev.get('id')}: {ev.get('name')}")
                
                ev_choice = input("Select evidence number to present: ").strip()
                if ev_choice.isdigit():
                    ev_idx = int(ev_choice) - 1
                    if 0 <= ev_idx < len(evidence_list):
                        selected_evidence = evidence_list[ev_idx]
                        evidence_id = selected_evidence.get("id")
                        
                        print(f"\n[Processing Action]: Presenting {evidence_id} against {stmt.get('id')}...")
                        
                        # Validação mecânica (pode usar o teu verify_candidate se desejares)
                        expected_ev = stmt.get("contradicted_by")
                        if expected_ev == evidence_id:
                            print(f"\n💥 OBJECTION! That's a direct contradiction!")
                            print(f"[JUDGE]: Sustained! The witness's statement cannot be true given the {selected_evidence.get('name')}.")
                            self.engine.trial_state.register_contradiction(stmt.get("id"), evidence_id)
                            # Se quebrou o testemunho, avançamos para a próxima fase com sucesso!
                            return self.engine.trial_state.next_phase_id(self.phase_id)
                        else:
                            print(f"\n[PENALTY]: The Judge bangs the gavel! Incorrect evidence.")
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