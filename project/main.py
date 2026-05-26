from __future__ import annotations

import argparse
import time
from pathlib import Path

from project.adaptation.config import AdaptationConfig
from project.common.types import TrialContext
from project.generation.candidate_generator import generate_candidates
from project.logs.logger import append_log
from project.prompts.prompt_builder import build_prompt
from project.retrieval.loader import build_documents, load_case_bundle
from project.retrieval.store import LocalRetriever, maybe_build_chroma_retriever
from project.ui.cli_demo import print_candidates
from project.verifier.symbolic_verifier import verify_candidate


def run_pipeline(
    repo_root: Path,
    case_id: str,
    query: str,
    tone: str,
    k: int,
    retrieval_k: int,
    use_chroma: bool,
) -> None:
    start = time.perf_counter()

    bundle = load_case_bundle(repo_root, case_id)
    docs = build_documents(bundle)

    retriever = None
    if use_chroma:
        retriever = maybe_build_chroma_retriever(docs)
    if retriever is None:
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
    candidates = generate_candidates(bundle=bundle, adaptation=adaptation, k=k)

    verified = [(cand, verify_candidate(bundle, cand)) for cand in candidates]
    valid_candidates = [cand for cand, verdict in verified if verdict.valid]

    elapsed_ms = int((time.perf_counter() - start) * 1000)

    log_file = repo_root / "project" / "logs" / "runtime.jsonl"
    append_log(
        log_file,
        {
            "case_id": case_id,
            "query": query,
            "retrieved_docs": [chunk.id for chunk in retrieved],
            "tone_used": tone,
            "selected_candidate": valid_candidates[0].candidate_id if valid_candidates else None,
            "valid_candidates": len(valid_candidates),
            "k": k,
            "response_time_ms": elapsed_ms,
        },
    )

    print("=== Prompt Preview ===")
    print(prompt)
    print_candidates(verified)
    print(f"\nLog written to: {log_file}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Courtroom AI core pipeline demo")
    parser.add_argument("--case-id", default="case_001")
    parser.add_argument("--query", default="Challenge statement stmt_3 with evidence")
    parser.add_argument("--tone", default="neutral", choices=["friendly", "neutral", "aggressive", "informative"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--use-chroma", action="store_true")
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
    )


if __name__ == "__main__":
    main()
