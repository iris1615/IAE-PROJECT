from __future__ import annotations
from dataclasses import dataclass
from project.knowledge.discovery_engine import DiscoveryEngine

@dataclass
class ActionResult:
    success: bool
    discovered_fact: str | None
    witness_stress: int
    next_state: str

class ActionResolver:
    def __init__(self, trial_state):
        self.trial_state = trial_state
        self.discovery_engine = DiscoveryEngine(trial_state)

    def resolve_action(self, action: str, statement_id: str, evidence_id: str) -> ActionResult:
        """Processes the structural action strictly against Phase 7 solution data formats."""
        if action != "PRESENT":
            return ActionResult(False, None, 0, "CONTINUE")

        testimonies = self.trial_state.bundle.get("testimonies", [])
        if isinstance(testimonies, dict):
            testimonies = [testimonies]
            
        chosen_solution = None
        current_witness_id = None

        for t in testimonies:
            for stmt in t.get("statements", []):
                if stmt.get("id") == statement_id:
                    current_witness_id = t.get("witness_id")
                    # Backward-compatible check supporting rich solution blocks or legacy properties
                    solutions = stmt.get("solutions", [])
                    if not solutions and stmt.get("correct_evidence") == evidence_id:
                        solutions = [{"evidence": evidence_id, "reveals_fact": f"fact_{statement_id}", "stress_damage": 3}]
                    
                    for sol in solutions:
                        if sol.get("evidence") == evidence_id:
                            chosen_solution = sol
                            break

        if chosen_solution:
            fact_to_reveal = chosen_solution.get("reveals_fact", f"fact_{statement_id}")
            stress_dmg = int(chosen_solution.get("stress_damage", 3))
            
            # Execute deterministic modifications
            self.discovery_engine.reveal_fact(fact_to_reveal)
            self.trial_state.contradictions_found.append(statement_id)
            
            if current_witness_id in self.trial_state.witness_states:
                self.trial_state.witness_states[current_witness_id].apply_damage(stress_dmg)

            self.trial_state.record_choice({
                "statement_id": statement_id,
                "evidence_id": evidence_id,
                "verdict_valid": True,
                "discovered_fact": fact_to_reveal
            })

            return ActionResult(
                success=True,
                discovered_fact=fact_to_reveal,
                witness_stress=stress_dmg,
                next_state="ARGUMENT"
            )
        else:
            # Rejection mechanisms directly managed by strict systemic rules
            self.trial_state.apply_penalty(1)
            self.trial_state.record_choice({
                "statement_id": statement_id,
                "evidence_id": evidence_id,
                "verdict_valid": False,
                "discovered_fact": None
            })
            return ActionResult(False, None, 0, "FAIL")