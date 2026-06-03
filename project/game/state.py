# project/game/state.py
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Set

class WitnessState:
    def __init__(self, w_id: str, name: str, data: dict):
        personality = data.get("personality", {})
        self.witness_id = w_id
        self.name = name
        self.stress = int(personality.get("anxiety", 4))
        self.credibility = int(personality.get("confidence", 7))
        self.patience = int(personality.get("patience", 5))
        self.cornered = False

    def apply_damage(self, stress_dmg: int):
        self.stress = min(10, self.stress + stress_dmg)
        self.credibility = max(0, self.credibility - stress_dmg)
        self.cornered = True


class TrialState:
    def __init__(self, bundle: dict, log_file: Path | None = None):
        self.bundle = bundle
        self.log_file = log_file
        self.phases = {p["id"]: p for p in bundle["case"].get("phases", [])}
        
        # Narrative and Core Flow Controls
        self.penalties: int = 0
        self.max_penalties: int = 3
        self.player_choices: List[Dict[str, Any]] = []
        
        # Architectural Rich State Infrastructure
        self.discovered_facts: Set[str] = set()
        self.contradictions_found: List[str] = []
        self.witness_states: Dict[str, WitnessState] = {}
        self.verdict_progress: float = 0.0
        
        self._init_witnesses()

    def _init_witnesses(self) -> None:
        witnesses_obj = self.bundle.get("witnesses", {})
        if isinstance(witnesses_obj, dict):
            for w_id, w_data in witnesses_obj.items():
                if isinstance(w_data, dict):
                    self.witness_states[w_id] = WitnessState(w_id, w_data.get("name", w_id), w_data)

    def record_choice(self, choice_data: dict):
        self.player_choices.append(choice_data)
        self._write_log(choice_data)

    def apply_penalty(self, amount: int = 1):
        self.penalties += amount
        print(f"\n[ PENALTY]: The Judge bangs the gavel! Penalties: {self.penalties}/{self.max_penalties}")
        if self.penalties >= self.max_penalties:
            print("\n GAVEL BANG! Game Over: The defendant was found GUILTY due to defense misconduct.")
            sys.exit(0)

    def next_phase_id(self, current_phase_id: str) -> str | None:
        phases_list = self.bundle["case"].get("phases", [])
        current_idx = next((i for i, p in enumerate(phases_list) if p["id"] == current_phase_id), -1)
        
        if current_idx == -1 or current_idx == len(phases_list) - 1:
            return None
            
        next_phase = phases_list[current_idx + 1]
        
        if next_phase.get("type") == "VERDICT":
            reqs = next_phase.get("conditions", {}).get("required_contradictions", [])
            # Structural evaluation based on factual metrics
            success = all(c in self.contradictions_found for c in reqs) or len(self.contradictions_found) > 0
            if success:
                print("\n[VERDICT]: Irrefutable evidence presented! The Defendant is... ACQUITTED!")
            else:
                print("\n[VERDICT]: Insufficient contradictions raised. The Defendant is... GUILTY!")
            return None

        return next_phase["id"]

    def _write_log(self, data: dict) -> None:
        if self.log_file:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(data) + "\n")
            except Exception:
                pass