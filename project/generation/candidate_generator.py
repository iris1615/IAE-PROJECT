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

    # now ollama is used by default
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
