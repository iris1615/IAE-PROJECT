from __future__ import annotations
from project.game.engine_reactions import build_npc_reactions

class ReactionGenerator:
    def __init__(self, engine):
        self.engine = engine

    def generate_reactions(self, candidate, verdict_valid: bool, phase_type: str):
        from project.common.types import VerifierResult
        dummy_verdict = VerifierResult(valid=verdict_valid, reason="ok")
        
        return build_npc_reactions(
            bundle=self.engine.bundle,
            candidate=candidate,
            verdict=dummy_verdict,
            adaptation=self.engine.adaptation_config,
            history=self.engine.trial_state.player_choices,
            ollama_model=self.engine.ollama_model,
            phase=phase_type
        )