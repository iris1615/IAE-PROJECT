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

### Prerequisites

- Install [Ollama](https://ollama.com/) locally.
- Download the model used by the game loop:

```bash
ollama pull llama3:8b
```

- Make sure the Ollama service is running before starting the pipeline.

1. (Optional) create environment and install deps:

```bash
pip install -r project/requirements.txt
```

2. Run demo:

```bash
#run complete flow
python -m project.main --case-id case_001

#test a specific statement
python -m project.main --case-id case_001 --query "Challenge witness statement stmt_3"
```

## Development: watcher and iterative testing

When you are editing `cases/`, `schemas/` or `project/prompts/` and want the Chroma collections to update automatically, run the reindex watcher in a separate terminal. The watcher debounces rapid file changes and will call the local reindex logic with `force=True` when relevant files change.

Activate your virtualenv and install dependencies if you haven't already:

```bash
source .venv/bin/activate   # or your chosen venv activation
pip install -r project/requirements.txt
```

Start the watcher (from the repository root):

```bash
python -m project.retrieval.reindex_watcher
```

Notes:

- The watcher watches `cases/`, `schemas/`, and `project/prompts/`.
- It is intended for local development only (not production).
- If you prefer to reindex on-demand, run the pipeline with `--force-reindex`:

```bash
python -m project.main --case-id case_001 --use-chroma --force-reindex
```

Stopping the watcher: press `Ctrl+C` in the terminal running it.

Logging and replay

- Runtime events (player choices and the final verdict) are appended to `project/logs/runtime.jsonl`.
- Final closing argument and final verdict are persisted into the runtime log for easy replay and analysis.

Tips

- If `ollama` is not installed or the model is unavailable, the code falls back to local template-based generators. Use `--no-ollama` to force template mode for deterministic testing.
- To speed up iteration, run the watcher in a separate terminal while you edit cases; the pipeline will pick up reindexed collections automatically.

## Notes

- The pipeline works without external APIs by using a deterministic local candidate generator.
- If you later add OpenAI/other LLM calls, keep the same interfaces and only swap `generation/candidate_generator.py` internals.
- Keep retrieval `k` small (2-5) to avoid prompt bloat.
