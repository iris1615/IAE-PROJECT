from typing import List

from project.adaptation.config import AdaptationConfig
from project.common.types import RetrievedChunk, TrialContext


def build_prompt(
    context: TrialContext,
    adaptation: AdaptationConfig,
    retrieved: List[RetrievedChunk],
) -> str:
    evidence_block = "\n".join(
        [f"- [{chunk.id}] ({chunk.metadata.get('kind', 'unknown')}): {chunk.content}" for chunk in retrieved]
    )

    return f"""
SYSTEM:
You are the prosecutor in a courtroom game. Stay grounded in provided facts only.

PERSONALITY:
Use tone '{adaptation.tone}' with strictness={adaptation.judge_strictness}.

CASE FACTS:
- Case ID: {context.case_id}
- Case Title: {context.case_title}
- Summary: {context.summary}

CURRENT TRIAL STATE:
- Phase: {context.current_phase}
- Player action: {context.player_action}

RETRIEVED EVIDENCE:
{evidence_block if evidence_block else '- none'}

TASK:
Generate 5 distinct objection candidates as JSON array.
Each candidate must include: tone, target_statement_id, evidence_id, argument.
Avoid unsupported claims.

NOTE:
Avoid using internal IDs or variable names (for example: stmt_3, security_photo) in the human-facing text. Use natural, in-universe phrasing (e.g. "the witness' statement" or "the hallway security photo").
""".strip()
