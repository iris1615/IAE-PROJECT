# AI Courtroom Core Pipeline (MVP)

Small, modular, and demonstrable pipeline for grounded courtroom dialogue driven by Local LLMs (Ollama) and Symbolic Verification.

## Implemented Modules

- `retrieval/`: JSON ingestion and semantic retrieval (Chroma-ready, with a robust local fallback).
- `prompts/`: Dynamic prompt builder. Injects trial context, specific witness behavior rules, and strict negative constraints against lore-breaking.
- `generation/`:
  - `DialogueGenerator`: Dynamically generates custom Defense interrogation lines and witness responses split by stress windows (`0-5` Evasive/Uneasy, `6-7` Slipping/Partial Secret Bleed, `8-10` Totally Cornered/Full Secret Confession).
  - `K-Candidate Generation`: K-candidate strategy generation (`k=5` default) with an integrated one-call strategy.
- `adaptation/`: Central adaptation config (tone, difficulty hooks, and character persona locking).
- `verifier/`: Dual-layer symbolic grounding and contradiction checks — instantly rejects LLM-generated team arguments that lack matching factual cues.
- `game/phase_manager.py`: Core game engine. Handles the cross-examination loop, navigation logic, witness damage mechanics, and the final Closing Argument phase.
- `logs/`: JSONL experiment, player choices, and runtime events logging (`runtime.jsonl`).
- `ui/`: Lightweight interactive CLI courtroom demo loop.

## Quick Start

### Prerequisites

- Install [Ollama](https://ollama.com/) locally.
- Download the base model utilized by the game loop:

```bash
ollama pull llama3:8b
```

* Make sure the Ollama service is running before starting the pipeline.

### Running the Loop

1. (Optional) Create a virtual environment and install dependencies:

**Bash**

```bash
source .venv/bin/activate   # or your chosen venv activation
pip install -r project/requirements.txt
```

2. Run the complete case demo flow (The Pastel de Nata and Monopoly money incident)[cite: 6]:

**Bash**

```bash
python -m project.main --case-id case_001
```

3. Test a specific statement contradiction via direct CLI query:

**Bash**

```bash
python -m project.main --case-id case_001 --query "Challenge witness statement stmt_3"
```

# Running Streamlit app

In a terminal window on the folder project/src run the following command:

```bash
streamlit run app.py
```

Then, open another terminal to run the backend at the same time using the same command above:

```bash
python -m project.main --case-id case_001
```

## System Mechanics & Balance Updates

### 🔄 Dynamic Pressing (Stress 6+ Mechanics)

The `Press Witness` action [1] is no longer a static text loop.

1. The Defense Attorney builds a contextual accusation on the fly matching the chosen statement.
2. The active witness's stress increment is gated to a controlled `+1` per press.
3. Upon hitting  **Stress level 6 or higher** , the witness cracks, causing their unique `hidden_information` block from their JSON profile to bleed directly into their spoken lines (e.g., Kip Hunter admitting her hidden Monopoly obsession).

### Anti-Hallucination Closing Argument

The final `Closing Argument` is generated using a lower `temperature=0.5` setting and is anchored strictly to the `discovered_facts` array. The local LLM is forbidden by explicit negative prompts from inventing unrelated severe crimes (like random murders, dark office windows, or mysterious phone calls) outside the scope of the actual case file.

### Developer Iteration & Fallbacks

* If `ollama` is not running or a model timeout occurs, the codebase automatically catches the exception and falls back to local, template-based deterministic responses so the game loop never crashes. Use `--no-ollama` to force this testing environment.
* To run the update the database just run the setup_chroma.py:
  ```
  python setup_chroma.py
  ```

### Input for the game

* in phase_manager.py there is a flagg (cli_flagg) that turns the input mode to either CLI or UI
* cli_flagg = True - input mode turned to cli
* cli_flagg = Flase - input mode turned to ui
  To run the UI just run in a terminal: streamlit run project/src/app.py

## Reset app state

* In the UI, at the debug area, there is 2 buttons:

- The first, reset app state, clear the streamlit variables, runtime.jsonl and input.jsonl, bassicly reseting the ui part of the current session, it doesnt reset the session, it just doesnt show history data.
- The second, reset user data, clears the user_info.json, deleting all the user data (action done and specific time)
