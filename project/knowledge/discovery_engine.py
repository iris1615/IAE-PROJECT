from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from project.game.state import TrialState

class DiscoveryEngine:
    def __init__(self, trial_state: TrialState):
        self.trial_state = trial_state

    def reveal_fact(self, fact_id: str) -> bool:
        """Adds an unlocked fact to the state tracker and updates analytical progress metrics."""
        if not fact_id or fact_id in self.trial_state.discovered_facts:
            return False
        self.trial_state.discovered_facts.add(fact_id)
        # Dynamically updates verdict progression metrics
        total_facts = len(self.trial_state.bundle.get("truth", {}).get("facts", [])) or 1
        self.trial_state.verdict_progress = len(self.trial_state.discovered_facts) / total_facts
        return True