from typing import List, Optional

from project.adaptation.config import AdaptationConfig
from project.common.types import RetrievedChunk, TrialContext


def build_prompt(
    context: TrialContext,
    adaptation: AdaptationConfig,
    retrieved: List[RetrievedChunk],
    known_truths: Optional[List[str]] = None,
    proven_steps: Optional[List[str]] = None,
    evidence_unlocks: Optional[List[str]] = None,
) -> str:
    evidence_block = "\n".join(
        [f"- [{chunk.id}] ({chunk.metadata.get('kind', 'unknown')}): {chunk.content}" for chunk in retrieved]
    )
    truths_block = "\n".join(f"- {truth}" for truth in (known_truths or []))
    steps_block = "\n".join(f"- {step}" for step in (proven_steps or []))
    unlocks_block = "\n".join(f"- {unlock}" for unlock in (evidence_unlocks or []))

    # The player is always the defense attorney in this game.
    role = "defense attorney"
    role_natural = role

    return f"""
SYSTEM:
You are the defense attorney in a courtroom game. Stay grounded in provided facts only.

CRITICAL LOGICAL CONSTRAINTS (ANTI-PRECOGNITION):
1. You are analyzing ONE specific statement from a witness right now (defined in CURRENT TRIAL STATE / player action).
2. NEVER assume facts, events, or contexts that the witness has not explicitly mentioned yet in this specific statement.
3. DO NOT invent backstory elements (such as "waiting in lines", "random encounters", or specific interactions) unless they are explicitly present in the targeted statement or the retrieved evidence.
4. Your arguments must attack the PLAUSIBILITY, LOGIC, or CREDIBILITY of the isolated statement text itself, or connect it directly to concrete retrieved evidence. Do not extrapolate into future phases or unmentioned events.

PERSONALITY:
Use tone '{adaptation.tone}' with strictness={adaptation.judge_strictness}.

CASE FACTS:
- Case ID: {context.case_id}
- Case Title: {context.case_title}
- Summary: {context.summary}

CURRENT TRIAL STATE:
- Phase: {context.current_phase}
- Player action: {context.player_action}  <-- THIS IS YOUR EXCLUSIVE FOCUS

KNOWN CASE TRUTHS:
{truths_block if truths_block else '- none yet'}

PROVEN DEFENSE STEPS:
{steps_block if steps_block else '- none yet'}

CURRENT PHASE UNLOCKS:
{unlocks_block if unlocks_block else '- none'}

RETRIEVED EVIDENCE:
{evidence_block if evidence_block else '- none'}

TASK:
Generate 5 distinct argument candidates as a JSON array.
Each candidate must include these fields: `strategy`, `target_statement_id`, `evidence_id`, `argument`.
`argument` should be a single natural-sounding line the defense attorney would say (human-facing); avoid using internal IDs or variable names in that line.

Every argument must be directly grounded in the text under review. If a strategy (e.g., credibility or timeline) does not have a natural, factual anchor in the current statement, build the argument strictly around the lack of evidence or the absurdity of the statement's narrow scope, without hallucinating external surrounding events.

When you are defending the defendant, every argument must move toward innocence or reasonable doubt. Do not write arguments that suggest the defendant is guilty, reckless, or knowingly used fake currency. Prefer arguments that:
- challenge whether the witness actually saw what they claim;
- separate the existence of counterfeit money from the defendant's knowledge of it;
- identify another plausible actor who could have planted or switched the bill;
- use contradictions between testimony, evidence, and timeline to weaken the prosecution's conclusion.

If you are instructed to act as the defense attorney, prioritize arguments that support the defendant's innocence, raise reasonable doubt, challenge the prosecution's inference links, or highlight exculpatory interpretations of the facts. Avoid producing arguments that concede the defendant's guilt or that assert guilt as the primary conclusion.

Use the known truths and proven defense steps to advance the theory of innocence step by step. If a truth is already supported by concrete evidence or a successful prior contradiction, build on it rather than re-arguing it from scratch. If a next actor is implied by the evidence, move the reasoning toward identifying that actor instead of staying at the level of generic disbelief.

PRIORITIZE EVIDENCE FOR REASONING:
- When building arguments, prefer concrete retrieved evidence items (those with metadata kind 'evidence') as the primary factual anchors.
- If the retrieval also includes `truth` or `fact` items, treat those as higher-level conclusions that should only be invoked if you can cite a concrete piece of evidence that "unlocks" or supports that truth. For each argument, indicate which truth IDs (if any) the argument would justify unlocking.

OUTPUT EXTENSION (optional):
- In addition to the required fields, you may include an optional `unlocks_truth_ids` array listing `truth`/`fact` IDs the argument supports. This field is optional but recommended when the argument provides a path to establish a hidden truth from concrete evidence.
 - Optionally include a boolean field `present_evidence` indicating whether the argument should present the evidence item (true/false), and a numeric `presentation_score` between 0.0 and 1.0 expressing how central/strong the evidence is for this argument. If omitted, assume `present_evidence: true` and `presentation_score: 0.0`.

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
