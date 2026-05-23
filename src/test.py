from adaptation_controller import AdaptationAndEvaluationLead


if __name__ == "__main__":
    # Initialize Member 4's module
    m4_engine = AdaptationAndEvaluationLead(alpha=0.3, epsilon=0.1)
    
    # Mock character files passed from Member 1 / loaded from disk
    mock_judge = {"name": "Judge Judy", "personality": {"strictness": 5}}
    mock_prosecutor = {"name": "Lucien Valen", "personality": {"aggression": 9, "sarcasm": 7}}
    
    print("=== MEMBER 4 STANDALONE ADAPTATION LOOP RUNTIME INITIALIZATION ===")
    
    # Simulation step 1: Player commits a quick presentation error
    print("\n--- Telemetry Event 1: Player presents invalid evidence quickly ---")
    context_before = m4_engine._get_context_state()
    frustration = m4_engine.estimate_player_state(is_mistake=True, response_time_seconds=8.5)
    bandit_action = m4_engine.select_bandit_action()
    
    print(f"EMA Frustration Rating: {frustration} | Action Chosen by Bandit: {bandit_action}")
    
    # Apply modifications
    j_mod, p_mod = m4_engine.control_dynamic_difficulty(bandit_action, mock_judge, mock_prosecutor)
    print(f"Adjusted Prosecutor Aggression: {p_mod['personality']['aggression']}/10")
    
    # Log this step to the evaluation data system
    m4_engine.log_experimental_step("case_001", "cross_exam_1", bandit_action, system_ablation_active=False)
    
    # Simulation step 2: Player gets stuck, waits long, makes another error
    print("\n--- Telemetry Event 2: Player gets deeply stuck and makes another error ---")
    context_before = m4_engine._get_context_state()
    frustration = m4_engine.estimate_player_state(is_mistake=True, response_time_seconds=52.0)
    bandit_action = m4_engine.select_bandit_action()
    
    print(f"EMA Frustration Rating: {frustration} | Action Chosen by Bandit: {bandit_action}")
    
    j_mod, p_mod = m4_engine.control_dynamic_difficulty(bandit_action, mock_judge, mock_prosecutor)
    print(f"Adjusted Prosecutor Aggression Level: {p_mod['personality']['aggression']}/10")
    print(f"Adjusted Judge Strictness Level: {j_mod['personality']['strictness']}/10")
    
    # Record history logs
    m4_engine.log_experimental_step("case_001", "cross_exam_1", bandit_action, system_ablation_active=False)
    print(f"\nEvaluation File successfully populated at: '{m4_engine.log_path}'")