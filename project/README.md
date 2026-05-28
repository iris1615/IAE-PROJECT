# AI Core Pipeline (MVP)

Small, modular, and demonstrable pipeline for grounded courtroom dialogue.

## Implemented modules

- `retrieval/`: JSON ingestion and retrieval (Chroma-ready, local fallback available)
- `prompts/`: prompt builder with trial context and retrieved evidence
- `generation/`: K-candidate generation (`k=5` default) with one-call strategy
- `adaptation/`: central adaptation config (tone, difficulty hooks)
- `verifier/`: symbolic grounding and contradiction checks
- `logs/`: JSONL experiment and runtime logging
- `ui/`: tiny CLI demo loop

## Quick start

1. (Optional) create environment and install deps:

```bash
pip install -r project/requirements.txt
```

2. Run demo:

```bash
python -m project.main --case-id case_001 --query "Challenge witness statement stmt_3"

#usa chroma DB e ollama model
python -m project.main --case-id case_001 --query "Challenge witness statement stmt_3" --use-chroma --use-ollama --ollama-model llama3:8b
```

## Notes

- The pipeline works without external APIs by using a deterministic local candidate generator.
- If you later add OpenAI/other LLM calls, keep the same interfaces and only swap `generation/candidate_generator.py` internals.
- Keep retrieval `k` small (2-5) to avoid prompt bloat.
