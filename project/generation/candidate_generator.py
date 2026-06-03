from __future__ import annotations

from typing import Dict, List

from project.adaptation.config import AdaptationConfig
from project.common.types import CandidateArgument
from typing import Optional

try:
    from project.generation.ollama_client import ollama_generate_json
except Exception:
    ollama_generate_json = None


def _evidence_items(bundle: Dict) -> List[Dict]:
    evidence = bundle.get("evidence", {})
    if isinstance(evidence, list):
        return [item for item in evidence if isinstance(item, dict)]
    if isinstance(evidence, dict) and evidence.get("id"):
        return [evidence]
    return []


def _pick_evidence(bundle: Dict, target_stmt: Dict) -> Dict:
    items = _evidence_items(bundle)
    if not items:
        return {}

    expected_evidence_id = target_stmt.get("contradicted_by")
    if expected_evidence_id:
        for item in items:
            if item.get("id") == expected_evidence_id:
                return item

    return items[0]


def _testimony_items(bundle: Dict) -> List[Dict]:
    testimonies = bundle.get("testimonies", {})
    if isinstance(testimonies, list):
        return [item for item in testimonies if isinstance(item, dict)]
    if isinstance(testimonies, dict):
        if testimonies.get("statements"):
            return [testimonies]
        return [item for item in testimonies.values() if isinstance(item, dict)]
    return []


def _score_evidence(evidence: Dict, target_stmt: Dict, timeline_text: str, fact_texts: List[str]) -> float:
    """Simple heuristic to score how useful an evidence item is for contradicting or supporting a target statement.

    Returns a score in [0.0, 1.0]. Higher means more useful to present.
    """
    if not evidence:
        return 0.0

    # If the statement explicitly lists this evidence as the contradicting item, it's maximally useful.
    contradicted_by = target_stmt.get("contradicted_by") if target_stmt else None
    if contradicted_by and contradicted_by == evidence.get("id"):
        return 1.0

    score = 0.0

    # Evidence that "reveals" concrete facts is more useful
    if evidence.get("reveals"):
        score += 0.5

    desc = (evidence.get("description") or "").lower()
    name = (evidence.get("name") or "").lower()

    # Objective artifacts (photos, footage, marked items, biometrics) are stronger anchors
    if any(k in desc for k in ("photo", "video", "footage", "security", "surveillance", "marked", "fingerprint", "dna", "receipt")):
        score += 0.4

    # If the evidence name or description echoes the statement text or timeline, boost slightly
    stmt_text = (target_stmt.get("text") if target_stmt else "") or ""
    if name and name in stmt_text.lower():
        score += 0.3
    for w in timeline_text.lower().split():
        if w and w in desc:
            score += 0.05
            break

    return min(score, 1.0)


def generate_candidates(
    bundle: Dict,
    adaptation: AdaptationConfig,
    k: int = 5,
    prompt: Optional[str] = None,
    use_ollama: bool = False,
    ollama_model: str = "llama3:8b",
    present_threshold: float = 0.5,
) -> List[CandidateArgument]:
    testimonies = _testimony_items(bundle)
    truth = bundle.get("truth", {})
    selected_testimony = testimonies[0] if testimonies else {"statements": []}
    selected_statements = selected_testimony.get("statements", [])
    valid_statement_ids = {stmt.get("id") for stmt in selected_statements if stmt.get("id")}

    # Pick a testimony that has a statement contradicted by an available evidence item.
    target_stmt = None
    evidence = {}
    for testimony in testimonies:
        for stmt in testimony.get("statements", []):
            contradicted_by = stmt.get("contradicted_by")
            if contradicted_by:
                evidence = next((item for item in _evidence_items(bundle) if item.get("id") == contradicted_by), {})
                if evidence:
                    target_stmt = stmt
                    selected_testimony = testimony
                    selected_statements = testimony.get("statements", [])
                    valid_statement_ids = {s.get("id") for s in selected_statements if s.get("id")}
                    break
        if target_stmt is not None:
            break

    if target_stmt is None:
        target_stmt = selected_statements[0] if selected_statements else {"id": "stmt_1", "text": ""}
        evidence = _pick_evidence(bundle, target_stmt)

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
                        
                        # 1. Extrair o ID enviado pelo Ollama
                        target_statement_id = item.get("target_statement_id")
                        
                        # --- CORREÇÃO: Tratar listas alucinadas pelo LLM onde llm_out ESTÁ definido ---
                        if isinstance(target_statement_id, list):
                            target_statement_id = target_statement_id[0] if target_statement_id else "stmt_1"
                        
                        # 2. Agora a verificação com o 'set' já não vai crashar
                        if target_statement_id not in valid_statement_ids:
                            target_statement_id = target_stmt.get("id", "stmt_1")
                        
                        candidates.append(
                            CandidateArgument(
                                candidate_id=f"cand_ollama_{idx+1}",
                                strategy=item.get("strategy") or item.get("tone") or strategies[idx % len(strategies)],
                                target_statement_id=target_statement_id,
                                evidence_id=canonical_evidence_id,
                                argument=item.get("argument") or item.get("dialogue") or "",
                                present_evidence=item.get("present_evidence", True),
                                presentation_score=item.get("presentation_score", 0.0),
                            )
                        )
                    return candidates
            # on failure, fall back to local templates
    
'''
Helper functions to generate differente arguments styles
'''
def _timeline_pressure_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[timeline/{tone}] The timeline does not prove the defendant knew the bill was fake; it only shows {evidence_name} "
        f"({evidence_description}) entered the scene at a relevant time, which still leaves open the possibility that someone else placed it there."
    )

def _credibility_attack_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[credibility/{tone}] The witness never identified the person near the pocket, so '{statement_text}' remains an uncertain observation rather than proof against the defendant."
    )

def _forensic_framing_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[forensic/{tone}] {evidence_name} may show the bill was counterfeit, but it does not by itself show the defendant knew that fact; the physical evidence proves the bill's condition, not the defendant's intent."
    )

def _logical_chain_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[logic/{tone}] Premise A: the bill was counterfeit. Premise B: there is no direct evidence the defendant knew it was fake. Therefore, guilt does not follow, because the missing step is knowledge, not the existence of a fake bill."
    )

def _judge_focused_argument(statement_text, evidence_name, evidence_description, timeline_text, fact_texts, tone):
    return (
        f"[court-record/{tone}] The record still leaves open a planted-bill theory: the testimony points to an unidentified figure near the pocket, and that is enough to create reasonable doubt about who introduced the counterfeit money."
    )
