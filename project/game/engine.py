from __future__ import annotations
from project.game.phase_manager import PhaseManager
from project.game.action_resolver import ActionResolver
from project.narrative.argument_generator import ArgumentGenerator
from project.narrative.reaction_generator import ReactionGenerator
from project.narrative.dialogue_generator import DialogueGenerator
from project.adaptation.config import AdaptationConfig

class GameEngine:
    def __init__(
        self, bundle: dict, retriever, trial_state, adaptation: AdaptationConfig, 
        ollama_model: str, use_ollama: bool = True, k: int = 5, retrieval_k: int = 3
    ):
        self.bundle = bundle
        self.retriever = retriever
        self.trial_state = trial_state
        self.adaptation_config = adaptation
        self.ollama_model = ollama_model
        self.use_ollama = use_ollama
        self.k = k
        self.retrieval_k = retrieval_k
        
        # Unified Architectural Dependency Wiring
        self.action_resolver = ActionResolver(self.trial_state)
        self.phase_manager = PhaseManager(self, retriever, trial_state, adaptation, ollama_model)
        
        # Narrative Module Initializations
        self.argument_generator = ArgumentGenerator(self)
        self.reaction_generator = ReactionGenerator(self)
        self.dialogue_generator = DialogueGenerator(self)

    def run(self) -> None:
        phases_list = self.bundle["case"].get("phases", [])
        if not phases_list:
            return

        current_phase_id = phases_list[0].get("id")
        while current_phase_id is not None:
            current_phase_id = self.phase_manager.execute_phase(current_phase_id)
            
        print("\n=== TRIAL SESSION CONCLUDED ===")