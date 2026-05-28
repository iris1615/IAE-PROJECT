# scripts/reindex_case.py
from pathlib import Path
from project.retrieval.loader import load_case_bundle, build_documents
from project.retrieval.chroma_indexer import ensure_chroma_index

repo = Path(".")
case_id = "case_001"
bundle = load_case_bundle(repo, case_id)
docs = build_documents(bundle)
ensure_chroma_index(repo, case_id, docs, force=False)