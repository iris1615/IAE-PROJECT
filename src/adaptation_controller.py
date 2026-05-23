import json
import os
import random
import time
from typing import Dict, Any, List, Tuple

class AdaptationAndEvaluationLead:
    def __init__(self, alpha: float = 0.25, epsilon: float = 0.1, log_path: str = "evaluation_results.json"):
        # --- EMA (Player Modeling) Parameters ---
        self.alpha = alpha  # Smoothing factor for latent state tracking
        self.latent_frustration = 0.0  # Kept between 0.0 (smooth) and 1.0 (frustrated)
        
        # --- Contextual Bandit Parameters ---
        self.epsilon = epsilon  # Exploration rate for bandit policy
        self.actions = ["BUFF_OPPONENT", "MAINTAIN_BASE", "NERF_OPPONENT", "TRIGGER_LENIENCY"]
        # Bandit Q-table structure to map discrete contexts to action values over time
        # Context Keys: 0 = Low Frustration, 1 = Medium Frustration, 2 = High Frustration
        self.q_table: Dict[int, Dict[str, float]] = {
            0: {a: 0.0 for a in self.actions},
            1: {a: 0.0 for a in self.actions},
            2: {a: 0.0 for a in self.actions}
        }
        
        # --- Evaluation & Ablation Tracking ---
        self.log_path = log_path
        self.experiment_history: List[Dict[str, Any]] = []

    # =========================================================================
    # DELIVERABLE 1: EMA Latent State Estimator
    # =========================================================================
    def estimate_player_state(self, is_mistake: bool, response_time_seconds: float) -> float:
        """
        Calculates immediate interaction friction and updates the Latent State via EMA.
        Formula: State_t = (alpha * Immediate_Friction) + ((1 - alpha) * State_t-1)
        """
        # Quantify instant stress: mistakes cause spikes; slow response times add subtle weight
        time_factor = min(0.3, response_time_seconds / 60.0)
        mistake_factor = 0.7 if is_mistake else 0.0
        
        immediate_friction = min(1.0, mistake_factor + time_factor)
        
        # Apply the Exponential Moving Average formula
        self.latent_frustration = (self.alpha * immediate_friction) + ((1 - self.alpha) * self.latent_frustration)
        return round(self.latent_frustration, 4)

    # =========================================================================
    # DELIVERABLE 2: Contextual Bandit Policy
    # =========================================================================
    def _get_context_state(self) -> int:
        """Converts continuous EMA score to a discrete bandit context profile."""
        if self.latent_frustration < 0.35:
            return 0  # Low Frustration / Skillful
        elif self.latent_frustration < 0.70:
            return 1  # Moderate Frustration / Normal
        return 2      # High Frustration / Struggling

    def select_bandit_action(self) -> str:
        """
        Contextual Bandit selection utilizing an Epsilon-Greedy Exploration/Exploitation balance.
        """
        context = self._get_context_state()
        
        # Explore: pick a random difficulty action
        if random.random() < self.epsilon:
            return random.choice(self.actions)
        
        # Exploit: pick the best performing action found in the Q-table for this context
        action_rewards = self.q_table[context]
        best_action = max(action_rewards, key=action_rewards.get)
        return best_action

    def update_bandit_knowledge(self, context_before: int, action_taken: str, user_engagement_score: float):
        """Updates bandit value arrays based on the calculated reward parameter score."""
        # Simple temporal-difference tracking update rule
        learning_rate = 0.1
        current_q = self.q_table[context_before][action_taken]
        self.q_table[context_before][action_taken] = current_q + learning_rate * (user_engagement_score - current_q)

    # =========================================================================
    # DELIVERABLE 3: Adaptation Controller
    # =========================================================================
    def control_dynamic_difficulty(self, action: str, judge_profile: Dict[str, Any], prosecutor_profile: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Mutates game configuration profiles directly based on bandit directives.
        These are then fed down the pipeline to Member 2's system prompt generators.
        """
        # Create shallow map copies to maintain pure functional context transformations
        adj_judge = dict(judge_profile)
        adj_prosecutor = dict(prosecutor_profile)
        
        if action == "TRIGGER_LENIENCY":
            # Force compliance down with judge rule presets
            adj_judge["personality"]["strictness"] = max(1, adj_judge["personality"].get("strictness", 5) - 3)
            adj_prosecutor["personality"]["aggression"] = max(1, adj_prosecutor["personality"].get("aggression", 9) - 4)
            
        elif action == "NERF_OPPONENT":
            adj_prosecutor["personality"]["aggression"] = max(1, adj_prosecutor["personality"].get("aggression", 9) - 2)
            adj_prosecutor["personality"]["sarcasm"] = max(1, adj_prosecutor["personality"].get("sarcasm", 7) - 2)
            
        elif action == "BUFF_OPPONENT":
            # Increase aggression and prompt complexity to challenge top performers
            adj_prosecutor["personality"]["aggression"] = min(10, adj_prosecutor["personality"].get("aggression", 9) + 2)
            adj_judge["personality"]["strictness"] = min(10, adj_judge["personality"].get("strictness", 5) + 2)
            
        return adj_judge, adj_prosecutor

    # =========================================================================
    # DELIVERABLE 4: Evaluation Pipeline and Ablation Loggers
    # =========================================================================
    def log_experimental_step(self, case_id: str, phase_id: str, action_taken: str, system_ablation_active: bool):
        """
        Saves precise trial telemetry steps for ablation analysis and charts.
        Ablation tracking allows testing how the engine behaves with DDA turned off.
        """
        log_entry = {
            "timestamp": time.time(),
            "case_id": case_id,
            "phase_id": phase_id,
            "latent_frustration": self.latent_frustration,
            "bandit_action_selected": action_taken,
            "ablation_baseline_run": system_ablation_active
        }
        self.experiment_history.append(log_entry)
        
        # Continuous persistence to disk for runtime safe analytical execution
        with open(self.log_path, "w") as f:
            json.dump(self.experiment_history, f, indent=2)