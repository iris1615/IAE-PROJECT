from __future__ import annotations
from typing import Dict, Any

class DialogueGenerator:
    def __init__(self, engine):
        self.engine = engine

    def get_witness_data(self, witness_id: str) -> Dict[str, Any]:
        """Procura e devolve os dados da testemunha a partir do bundle do caso."""
        witnesses = self.engine.bundle.get("witnesses", {})
        
        if isinstance(witnesses, dict) and witness_id in witnesses:
            return witnesses[witness_id]
            
        if isinstance(witnesses, list):
            for w in witnesses:
                if isinstance(w, dict) and w.get("id") == witness_id:
                    return w
                    
        # Fallback in case its not in global map of bundle
        witness_state = self.engine.trial_state.witness_states.get(witness_id)
        if witness_state:
            return {
                "name": getattr(witness_state, "name", "Witness"),
                "personality": {"anxiety": getattr(witness_state, "anxiety", 5)},
                "hidden_information": [],
                "behavior_rules": [],
                "speech_style": {}
            }
            
        return {}

    def call_ollama(self, prompt: str) -> str:
        """Faz a chamada direta à API ou SDK do Ollama configurado no motor."""
        try:
            import ollama
            model_name = getattr(self.engine, "ollama_model", "llama3:8b")
            
            response = ollama.chat(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.7}
            )
            return response['message']['content'].strip()
        except Exception as e:
            return f"[Witness]: \"... I have nothing to say to that charge!\" (Ollama Error: {e})"

    def generate_press_response(self, witness_id: str, stress_level: int) -> str:
        # load witnesses profiles
        witness_data = self.get_witness_data(witness_id) 
        witness_name = witness_data.get("name", "Witness")
        occupation = witness_data.get("occupation", "Unknown")
        hidden_info = witness_data.get("hidden_information", [])
        behavior = witness_data.get("behavior_rules", [])
        style = witness_data.get("speech_style", {})
        
        hidden_info_str = "\n".join([f"- {info}" for info in hidden_info])
        behavior_str = "\n".join([f"- {b}" for b in behavior])

        # parcial revelation when stress 6+
        if stress_level >= 6:
            # mood tag based on stress
            mood_tag = "TOTALLY CORNERED" if stress_level >= 8 else "NERVOUS/SLIPPING"
            
            prompt = (
                f"You are simulating the witness '{witness_name}' in an Ace Attorney courtroom trial.\n"
                f"CRITICAL CHARACTER DATA:\n"
                f"- Name: {witness_name}\n"
                f"- Occupation: {occupation} (Do NOT change this. If they are a Student/Cashier, they are NOT a businessman!)\n"
                f"- Speech Style: {style}\n"
                f"- Behavior: {behavior_str}\n\n"
                f"SITUATION:\n"
                f"The defense attorney is pressing you hard. Your stress level is {stress_level}/10.\n"
                f"You are breaking under pressure. You MUST crack and explicitly admit one of your hidden secrets out loud to the court right now.\n\n"
                f"YOUR HIDDEN INFORMATION (You must ONLY reveal what is written here, NEVER borrow secrets from other characters):\n"
                f"{hidden_info_str}\n"
                f"STRICT RULES:\n"
                f"1. Do NOT invent new facts. If the secret says they are a big fan of Monopoly and collect the money, they must confess EXACTLY that.\n"
                f"2. Do NOT say you are a business owner or a man if your occupation is Student.\n"
                f"3. Keep it to 1-2 emotional, pressured sentences.\n"
                f"4. Format the output exactly like this: [{witness_name} ({mood_tag})]: \"[Your text here]\""
            )

        # evasive, low stress
        else:
            prompt = (
                f"You are simulating the witness '{witness_name}' in an Ace Attorney courtroom.\n"
                f"Profile: Name={witness_name}, Occupation={occupation}.\n"
                f"Current Stress: {stress_level}/10 (Mood: UNEASY).\n"
                f"The defense is pressing you. Do NOT reveal the core hidden secrets yet. Be evasive and slightly nervous, sticking strictly to your background.\n"
                f"Format the output exactly like this: [{witness_name} (UNEASY)]: \"[Your text here]\""
            )

        # Chamar a tua infraestrutura do Ollama...
        response = self.call_ollama(prompt)
        return response