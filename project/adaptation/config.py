from dataclasses import asdict, dataclass
from typing import Dict


@dataclass
class AdaptationConfig:
    tone: str = "neutral"
    temperature: float = 0.4
    judge_strictness: float = 0.5
    hint_level: float = 0.5
    difficulty: int = 1

    def to_dict(self) -> Dict[str, float | int | str]:
        return asdict(self)
