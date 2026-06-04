from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class EvidenceDocument:
    id: str
    kind: str
    content: str
    metadata: Dict[str, Any]


@dataclass
class RetrievedChunk:
    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


@dataclass
class TrialContext:
    case_id: str
    case_title: str
    summary: str
    current_phase: str
    player_action: str


@dataclass
class CandidateArgument:
    candidate_id: str
    strategy: str
    target_statement_id: str
    evidence_id: str
    argument: str
    present_evidence: bool = True
    presentation_score: float = 0.0


@dataclass
class VerifierResult:
    valid: bool
    reason: str


@dataclass
class NPCReaction:
    npc_id: str
    npc_name: str
    role: str
    trigger: str
    mood: str
    text: str
