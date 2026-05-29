from __future__ import annotations

import argparse
import time
from pathlib import Path
from project.adaptation.config import AdaptationConfig
from project.common.types import TrialContext
from project.generation.candidate_generator import generate_candidates
from project.logs.logger import append_log
from project.reactions.engine import build_npc_reactions
from project.prompts.prompt_builder import build_prompt
from project.retrieval.loader import build_documents, load_case_bundle
from project.retrieval.store import LocalRetriever
from project.ui.cli_demo import choose_candidate, print_player_choices, print_reactions
from project.verifier.symbolic_verifier import verify_candidate
from project.retrieval.chroma_indexer import ensure_chroma_index, build_chroma_retriever


def run_pipeline(
    repo_root: Path,
    case_id: str,
    query: str,
    tone: str,
    k: int,
    retrieval_k: int,
    use_chroma: bool,
    use_ollama: bool = False,
    ollama_model: str = "llama2:8b",
) -> None:
    start = time.perf_counter()

    bundle = load_case_bundle(repo_root, case_id)
    docs = build_documents(bundle)

    retriever = None
    if use_chroma:
        ensure_chroma_index(repo_root, case_id, docs)
        retriever = build_chroma_retriever(case_id)
    if retriever is None:
        #fallback to local retriever if chroma is not used or fails
        retriever = LocalRetriever(docs)

    retrieved = retriever.similarity_search(query, k=retrieval_k)

    adaptation = AdaptationConfig(tone=tone, difficulty=int(bundle["case"].get("difficulty", 1)))
    context = TrialContext(
        case_id=bundle["case"]["id"],
        case_title=bundle["case"]["title"],
        summary=bundle["case"]["summary"],
        current_phase="CROSS_EXAMINATION",
        player_action=query,
    )

    prompt = build_prompt(context=context, adaptation=adaptation, retrieved=retrieved)
    candidates = generate_candidates(
        bundle=bundle,
        adaptation=adaptation,
        k=k,
        prompt=prompt,
        use_ollama=use_ollama,
        ollama_model=ollama_model,
    )

    verified = [(cand, verify_candidate(bundle, cand, retrieved=retrieved)) for cand in candidates]
    valid_candidates = [cand for cand, verdict in verified if verdict.valid]
    player_choices = print_player_choices(verified)
    selected_candidate = choose_candidate(player_choices)
    reactions = []
    if selected_candidate is not None:
        selected_verdict = next((verdict for cand, verdict in verified if cand.candidate_id == selected_candidate.candidate_id), None)
        if selected_verdict is not None:
            print(f"\nSelected candidate: {selected_candidate.candidate_id} [{selected_candidate.strategy}]")
            reactions = build_npc_reactions(
                bundle=bundle,
                candidate=selected_candidate,
                verdict=selected_verdict,
                adaptation=adaptation,
            )

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    log_file = repo_root / "project" / "logs" / "runtime.jsonl"
    append_log(
        log_file,
        {
            "case_id": case_id,
            "query": query,
            "retrieved_docs": [chunk.id for chunk in retrieved],
            "tone_used": tone,
            "selected_candidate": selected_candidate.candidate_id if selected_candidate else None,
            "valid_candidates": len(valid_candidates),
            "npc_reactions": [reaction.text for reaction in reactions],
            "k": k,
            "response_time_ms": elapsed_ms,
        },
    )

    print("=== Prompt Preview ===")
    #print(prompt)
    print_reactions(reactions)
    print(f"\nLog written to: {log_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Courtroom AI core pipeline demo")
    parser.add_argument("--case-id", default="case_001")
    parser.add_argument("--query", default="Challenge statement stmt_3 with evidence")
    parser.add_argument("--tone", default="neutral", choices=["friendly", "neutral", "aggressive", "informative"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--use-chroma", action="store_true")
    parser.add_argument("--use-ollama", action="store_true", help="Use local Ollama model for candidate generation")
    parser.add_argument("--ollama-model", default="gemma4", help="Ollama model name to use (e.g. gemma4, llama2:8b)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    run_pipeline(
        repo_root=repo_root,
        case_id=args.case_id,
        query=args.query,
        tone=args.tone,
        k=args.k,
        retrieval_k=args.retrieval_k,
        use_chroma=args.use_chroma,
        use_ollama=args.use_ollama,
        ollama_model=args.ollama_model,
    )


if __name__ == "__main__":
    main()
