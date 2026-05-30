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
    ollama_model: str = "llama3:8b",
) -> List[CandidateArgument]:
    testimony = bundle["testimonies"]
    evidence = bundle["evidence"]
    truth = bundle.get("truth", {})
    valid_statement_ids = {stmt.get("id") for stmt in testimony.get("statements", []) if stmt.get("id")}

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

    strategies = ["timeline", "credibility", "forensic", "logic", "court-record"]
    candidates: List[CandidateArgument] = []

    # If user requested Ollama and client available, attempt a single LLM call to produce JSON candidates
    if use_ollama and prompt:
        # allow updating the module-level reference during lazy import
        global ollama_generate_json
        # If the top-level import failed previously, try importing lazily here and report the error.
        if ollama_generate_json is None:
            try:
                import importlib
                mod = importlib.import_module("project.generation.ollama_client")
                ollama_generate_json = getattr(mod, "ollama_generate_json", None)
                if ollama_generate_json is None:
                    print("[debug] Ollama client module imported but 'ollama_generate_json' not found. Falling back to templates.")
            except Exception as e:
                import traceback
                print("[debug] lazy import of Ollama client failed:")
                traceback.print_exc()
                print("[debug] Falling back to template candidate generation.")
        if ollama_generate_json is None:
            print("[debug] use_ollama=True but Ollama client is not available (ollama_generate_json is None). Falling back to templates.")
        else:
            print(f"[debug] use_ollama=True -> calling Ollama model='{ollama_model}' (prompt length={len(prompt)})")
            llm_out = ollama_generate_json(prompt=prompt, model=ollama_model, temperature=adaptation.temperature)
            if llm_out is None:
                print("[debug] Ollama returned no JSON (llm_out is None). Falling back to local templates.")
            else:
                print(f"[debug] Ollama returned JSON of type {type(llm_out)}; using LLM candidates.")
                # support single-object responses as well as lists
                if isinstance(llm_out, dict):
                    llm_out = [llm_out]
                if isinstance(llm_out, list):
                    canonical_evidence_id = evidence.get("id", "unknown_evidence")
                    for idx, item in enumerate(llm_out[:k]):
                        target_statement_id = item.get("target_statement_id")
                        if target_statement_id not in valid_statement_ids:
                            target_statement_id = target_stmt.get("id", "stmt_1")
                        candidates.append(
                            CandidateArgument(
                                candidate_id=f"cand_ollama_{idx+1}",
                                strategy=item.get("strategy") or item.get("tone") or strategies[idx % len(strategies)],
                                target_statement_id=target_statement_id,
                                evidence_id=canonical_evidence_id,
                                argument=item.get("argument") or item.get("dialogue") or "",
                            )
                        )
                    return candidates
            # on failure, fall back to local templates

    for idx in range(k):
        tpl = templates[idx % len(templates)]
        strategy = strategies[idx % len(strategies)]
        # Call template functions positionally to avoid signature mismatch
        arg_text = tpl(
            target_stmt.get("text", ""),
            evidence.get("name", evidence.get("id", "")),
            evidence.get("description", ""),
            timeline_text,
            fact_texts,
            strategy,
        )

        candidates.append(
            CandidateArgument(
                candidate_id=f"cand_{idx + 1}",
                strategy=strategy,
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
