from __future__ import annotations
import argparse
from pathlib import Path
from project.adaptation.config import AdaptationConfig
from project.retrieval.loader import build_documents, load_case_bundle
from project.retrieval.store import LocalRetriever
from project.retrieval.chroma_indexer import ensure_chroma_index, build_chroma_retriever
from project.game.state import TrialState
from project.game.engine import GameEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Courtroom AI architectural core pipeline")
    parser.add_argument("--case-id", default="case_001")
    parser.add_argument("--query", default="Challenge statement")
    parser.add_argument("--tone", default="neutral", choices=["friendly", "neutral", "aggressive", "informative"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--use-chroma", action="store_true")
    parser.add_argument("--no-ollama", dest="use_ollama", action="store_false")
    parser.set_defaults(use_ollama=True)
    parser.add_argument("--ollama-model", default="llama3:8b")
    parser.add_argument("--hint-level", type=float, default=0.9)
    parser.add_argument("--force-reindex", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    
    # 1. Load the case package (Case Bundle)
    bundle = load_case_bundle(repo_root, args.case_id)
    docs = build_documents(bundle)

    # 2. Setup storage/indexing retrieval layers
    retriever = None
    if args.use_chroma:
        ensure_chroma_index(repo_root, args.case_id, docs, force=args.force_reindex)
        retriever = build_chroma_retriever(args.case_id)
    if retriever is None:
        retriever = LocalRetriever(docs)

    # 3. Instantiate core game state systems
    adaptation = AdaptationConfig(tone=args.tone, difficulty=int(bundle["case"].get("difficulty", 1)), hint_level=args.hint_level)
    trial_state = TrialState(bundle, log_file=repo_root / "project" / "logs" / "runtime.jsonl")

    # 4. Fire the game loop orchester
    engine = GameEngine(
        bundle=bundle, retriever=retriever, trial_state=trial_state, adaptation=adaptation,
        ollama_model=args.ollama_model, use_ollama=args.use_ollama, k=args.k, retrieval_k=args.retrieval_k
    )
    engine.run()


if __name__ == "__main__":
    main()