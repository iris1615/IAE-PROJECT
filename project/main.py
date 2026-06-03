from __future__ import annotations
import argparse
from pathlib import Path
from project.adaptation.config import AdaptationConfig
from project.retrieval.loader import build_documents, load_case_bundle
from project.retrieval.store import LocalRetriever
from project.ui.cli_demo import choose_candidate, print_player_choices, print_reactions
from project.verifier.symbolic_verifier import verify_candidate
from project.retrieval.chroma_indexer import ensure_chroma_index, build_chroma_retriever
from project.game.state import TrialState
from project.game.engine import GameEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Courtroom AI architectural core pipeline")
    parser = argparse.ArgumentParser(description="Courtroom AI architectural core pipeline")
    parser.add_argument("--case-id", default="case_001")
    parser.add_argument("--query", default="Challenge statement")
    parser.add_argument("--query", default="Challenge statement")
    parser.add_argument("--tone", default="neutral", choices=["friendly", "neutral", "aggressive", "informative"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--retrieval-k", type=int, default=3)
    parser.add_argument("--use-chroma", action="store_true")
    parser.add_argument("--no-ollama", dest="use_ollama", action="store_false", help="Disable Ollama; use templates instead")
    parser.set_defaults(use_ollama=True)
    parser.add_argument("--ollama-model", default="llama3:8b")
    parser.add_argument("--hint-level", type=float, default=0.9)
    parser.add_argument("--force-reindex", action="store_true")
    parser.add_argument("--ollama-model", default="llama3:8b")
    parser.add_argument("--hint-level", type=float, default=0.9)
    parser.add_argument("--force-reindex", action="store_true")
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
        hint_level=args.hint_level,
        force_reindex=args.force_reindex,
    )
    engine.run()
    engine.run()


if __name__ == "__main__":
    main()