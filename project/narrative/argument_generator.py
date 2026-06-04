from __future__ import annotations
from project.common.types import TrialContext
from project.generation.prompt_builder import build_prompt
from project.generation.candidate_generator import generate_candidates

class ArgumentGenerator:
    def __init__(self, engine):
        self.engine = engine

    def generate_player_arguments(self, statement_id: str, evidence_id: str, discovered_fact: str | None) -> list:
        """Generates thematic dialog choices using Ollama, based on verified data."""
        query = f"Contradiction found in {statement_id} using evidence {evidence_id}. Fact revealed: {discovered_fact}"
        retrieved = self.engine.retriever.similarity_search(query, k=self.engine.retrieval_k)
        
        context = TrialContext(
            case_id=self.engine.bundle["case"]["id"],
            case_title=self.engine.bundle["case"]["title"],
            summary=self.engine.bundle["case"]["summary"],
            current_phase="CROSS_EXAMINATION",
            player_action=query,
        )
        
        prompt = build_prompt(
            context=context,
            adaptation=self.engine.adaptation,
            retrieved=retrieved,
            known_truths=list(self.engine.trial_state.discovered_facts),
            proven_steps=self.engine.trial_state.contradictions_found,
            evidence_unlocks=[evidence_id],
        )

        candidates = generate_candidates(
            bundle=self.engine.bundle,
            adaptation=self.engine.adaptation,
            k=self.engine.k,
            prompt=prompt,
            use_ollama=self.engine.use_ollama,
            ollama_model=self.engine.ollama_model,
        )
        return candidates