from __future__ import annotations

from typing import Dict, List

from project.adaptation.config import AdaptationConfig
from project.common.types import CandidateArgument
from typing import Optional

try:
    from project.generation.ollama_client import ollama_generate_json
except Exception:
    ollama_generate_json = None


def generate_candidates(
    bundle: Dict,
    adaptation: AdaptationConfig,
    k: int = 5,
    prompt: Optional[str] = None,
    use_ollama: bool = False,
    ollama_model: str = "llama2:8b",
) -> List[CandidateArgument]:
    testimony = bundle["testimonies"]
    evidence = bundle["evidence"]
    truth = bundle.get("truth", {})

    # pick the target statement (the one contradicted by this evidence when possible)
    target_stmt = None
    for stmt in testimony.get("statements", []):
        if stmt.get("contradicted_by") == evidence.get("id"):
            target_stmt = stmt
            break
    if target_stmt is None:
        target_stmt = testimony.get("statements", [{}])[0]

    # prepare context bits used by templates
    timeline = truth.get("timeline", [])
    timeline_text = ", ".join([f"{e.get('time','?')}: {e.get('event','')}" for e in timeline[:3]])
    fact_texts = [f.get("truth", "") for f in truth.get("facts", [])]

    # list of different argument-builder functions (each returns a string)
    templates = [
        _timeline_pressure_argument,
        _credibility_attack_argument,
        _forensic_framing_argument,
        _logical_chain_argument,
        _judge_focused_argument,
    ]

    tones = _tone_variants(adaptation.tone)
    candidates: List[CandidateArgument] = []

    # If user requested Ollama and client available, attempt a single LLM call to produce JSON candidates
    if use_ollama and prompt and ollama_generate_json is not None:
        llm_out = ollama_generate_json(prompt=prompt, model=ollama_model, temperature=adaptation.temperature)
        if isinstance(llm_out, list):
            for idx, item in enumerate(llm_out[:k]):
                candidates.append(
                    CandidateArgument(
                        candidate_id=f"cand_ollama_{idx+1}",
                        tone=item.get("tone", tones[idx % len(tones)]),
                        target_statement_id=item.get("target_statement_id", target_stmt.get("id", "stmt_1")),
                        evidence_id=item.get("evidence_id", evidence.get("id", "unknown_evidence")),
                        argument=item.get("argument", ""),
                    )
                )
            return candidates
        # on failure, fall back to local templates

    for idx in range(k):
        tpl = templates[idx % len(templates)]
        tone = tones[idx % len(tones)]
        # Call template functions positionally to avoid signature mismatch
        arg_text = tpl(
            target_stmt.get("text", ""),
            evidence.get("name", evidence.get("id", "")),
            evidence.get("description", ""),
            timeline_text,
            fact_texts,
            tone,
        )

        candidates.append(
            CandidateArgument(
                candidate_id=f"cand_{idx + 1}",
                tone=tone,
                target_statement_id=target_stmt.get("id", "stmt_1"),
                evidence_id=evidence.get("id", "unknown_evidence"),
                argument=arg_text,
            )
        )

    return candidates
    
'''
Helper functions to generate differente arguments styles
'''
def _timeline_pressure_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[timeline-pressure/{tone}] You say '{statement_text}'. "
        f"Recorded timeline ({timeline_text}) conflicts with that claim, and {evidence_name} "
        f"({evidence_description}) establishes a temporal mismatch."
    )

def _credibility_attack_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[credibility/{tone}] The witness claims '{statement_text}', a categorical denial. "
        f"But {evidence_name} directly contradicts that certainty — this weakens reliability."
    )

def _forensic_framing_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    detail = fact_texts[1] if len(fact_texts) > 1 else (fact_texts[0] if fact_texts else "")
    suffix = f" Note: {detail}." if detail else ""
    return (
        f"[forensic/{tone}] {evidence_name} is a material record: {evidence_description}. "
        f"It provides objective information that cannot be reconciled with '{statement_text}'.{suffix}"
    )

def _logical_chain_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[logic-chain/{tone}] Premise A: witness says '{statement_text}'. "
        f"Premise B: {evidence_name} records a conflicting condition. Therefore, the testimony and record "
        f"are inconsistent and require resolution."
    )

def _judge_focused_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[court-record/{tone}] For the court: statement ('{statement_text}') is challenged by {evidence_name}. "
        f"This is a material contradiction relevant to credibility and admissibility."
    )


def _tone_variants(base_tone: str) -> List[str]:
    base = base_tone.lower().strip()
    if base == "aggressive":
        return ["aggressive", "assertive", "sharp"]
    if base == "friendly":
        return ["friendly", "supportive", "calm"]
    if base == "informative":
        return ["informative", "analytical", "neutral"]
    return ["neutral", "assertive", "informative"]
