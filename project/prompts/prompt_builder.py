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
Generate 5 distinct objection candidates as a JSON array.
Each candidate must include these fields: `tone`, `target_statement_id`, `evidence_id`, `dialogue`.
`dialogue` should be a single natural-sounding line the prosecutor would say (human-facing); avoid using internal IDs or variable names in that line.
Make each candidate use a different rhetorical strategy (timeline, credibility, forensic, logic, court-record).
IMPORTANT: Surround the JSON output with these exact delimiters so the caller can extract it reliably:

<<<JSON_START>>>
<JSON array goes here>
<<<JSON_END>>>

Return ONLY the delimited JSON block (no surrounding commentary).

ADDITIONAL FORMAT REQUIREMENTS:
- Produce compact JSON (no pretty-printing or extra line breaks inside JSON strings).
- Escape any internal newlines inside string values as `\\n` (backslash + n), not as literal line breaks.

NOTE:
Avoid using internal IDs or variable names (for example: stmt_3, security_photo) in the human-facing text. Use natural, in-universe phrasing (e.g. "the witness' statement" or "the hallway security photo").
""".strip()
