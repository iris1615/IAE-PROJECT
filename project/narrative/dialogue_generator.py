# project/narrative/dialogue_generator.py
from __future__ import annotations

class DialogueGenerator:
    def __init__(self, engine):
        self.engine = engine

    def generate_press_response(self, witness_id: str, current_stress: int) -> str:
        """Injects expressive narration based directly upon structural witness stress values."""
        witness_data = self.engine.bundle.get("witnesses", {}).get(witness_id, {})
        name = witness_data.get("name", witness_id)
        
        if current_stress >= 8:
            return f'[{name} (TOTALLY CORNERED)]: "I... I don\'t know what to say! You found out everything..."'
        elif current_stress >= 5:
            return f'[{name} (NERVOUS)]: "That doesn\'t make any sense... there must be some mistake with your files!"'
        return f'[{name} (CALM)]: "I stand by my initial statement before this court."'