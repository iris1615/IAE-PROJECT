from __future__ import annotations

from typing import Dict, Optional, Tuple
from pathlib import Path

from project.logs.logger import append_log


class TrialState:
    def __init__(self, bundle: Dict, log_file: Optional[Path] = None):
        # bundle contains case and phases
        self.case = bundle.get("case", {})
        self.phases = {phase.get("id"): phase for phase in self.case.get("phases", [])}
        # record of player choices for persistence/playback
        self.player_choices: list[Dict] = []
        # where to append runtime events
        self.log_file: Path = log_file or (Path.cwd() / "project" / "logs" / "runtime.jsonl")

    def _find_phase_by_type(self, phase_type: str) -> Optional[Dict]:
        for phase in self.case.get("phases", []):
            if phase.get("type") == phase_type:
                return phase
        return None

    def next_phase_id(self, current_phase_id: str) -> Optional[str]:
        """Return the next phase id in the case's phases sequence after current_phase_id, or None."""
        phases = self.case.get("phases", [])
        for idx, phase in enumerate(phases):
            if phase.get("id") == current_phase_id:
                if idx + 1 < len(phases):
                    return phases[idx + 1].get("id")
                return None
        return None

    def apply_contradiction(self, current_phase: str, statement_id: str, evidence_id: str, success: bool) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Apply a contradiction attempt and return (next_phase_id, penalty, judge_response_key).
        Returns None for next_phase_id if no transition.
        """
        # find phase by id first, else by type
        phase = self.phases.get(current_phase) or self._find_phase_by_type(current_phase)
        if not phase:
            return None, None, None

        for contradiction in phase.get("contradictions", []):
            if contradiction.get("statement_id") == statement_id and contradiction.get("correct_evidence") == evidence_id:
                if success:
                    next_phase = contradiction.get("success", {}).get("next_phase")
                    penalty = contradiction.get("success", {}).get("penalty")
                    return next_phase, penalty, None
                else:
                    penalty = contradiction.get("failure", {}).get("penalty")
                    judge_response = contradiction.get("failure", {}).get("judge_response")
                    return None, penalty, judge_response

        return None, None, None

    def record_choice(self, candidate: Dict, verdict: Dict) -> None:
        """Append the player's chosen candidate and verifier verdict to the trial history."""
        entry = {
            "candidate_id": getattr(candidate, "candidate_id", None) or candidate.get("candidate_id"),
            "strategy": getattr(candidate, "strategy", None) or candidate.get("strategy"),
            "target_statement_id": getattr(candidate, "target_statement_id", None) or candidate.get("target_statement_id"),
            "evidence_id": getattr(candidate, "evidence_id", None) or candidate.get("evidence_id"),
            "argument": getattr(candidate, "argument", None) or candidate.get("argument"),
            "verdict_valid": getattr(verdict, "valid", None) or verdict.get("valid"),
            "verdict_reason": getattr(verdict, "reason", None) or verdict.get("reason"),
        }
        self.player_choices.append(entry)
        try:
            append_log(self.log_file, {"event": "player_choice", "choice": entry, "case_id": self.case.get("id")})
        except Exception:
            # Do not raise on logging failures; best-effort
            pass
