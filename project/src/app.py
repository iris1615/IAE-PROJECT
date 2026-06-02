import streamlit as st
import time
import sys
from pathlib import Path

# When running `streamlit run project/src/app.py`, Streamlit adds `project/src` to sys.path.
# Ensure the repo root is also on sys.path so `import project...` resolves correctly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from project.common.log_events import read_argument_options_events, read_dialogue_events, read_evidence_events, reset_log_events

# Streamlit requires page configuration to be set before other UI calls.
st.set_page_config(page_title="Ace Attorney AI", layout="wide")

# Timed refresh: re-run the script periodically so the UI reflects new backend events.
# Interval is in milliseconds.
from streamlit_autorefresh import st_autorefresh

st_autorefresh(interval=2000, key="timed_refresh")

# 1. INITIALIZE GAME STATE
# We use st.session_state so data survives the top-to-bottom script re-runs.
if "game_step" not in st.session_state:
    st.session_state.game_step = 0
if "case_id" not in st.session_state:
    st.session_state.case_id = "case_001"
if "dialogue_history" not in st.session_state:
    st.session_state.dialogue_history = []
if "telemetry_log" not in st.session_state:
    st.session_state.telemetry_log = []


def _repo_root() -> Path:
    # project/src/app.py -> parents[2] is repo root
    return Path(__file__).resolve().parents[2]


def _runtime_log_path() -> Path:
    return _repo_root() / "project" / "logs" / "runtime.jsonl"


def _render_evidence_card(title: str, description: str) -> None:
    st.info(f"**{title}**\n\n{description}")

# Function to simulate a click tracker for your telemetry requirement
def log_telemetry(action_type, detail):
    timestamp = time.time()
    st.session_state.telemetry_log.append({
        "timestamp": timestamp,
        "action": action_type,
        "detail": detail
    })

with st.container():
    # 2. CONFIGURE THE PAGE LAYOUT
    empty_left, center, empty_right = st.columns([1, 2, 1])
    
    with center:
        st.title("⚖️ Ace Attorney: Adaptive Courtroom")

with st.container():
    # 3/4. MIDDLE AREA: 3-WAY HORIZONTAL SPLIT
    # Left: Court Record | Middle: (empty for now) | Right: Courtroom Dialogue
    left_col, mid_col, right_col = st.columns([1,3,1])

    with left_col:
        st.header("🗂️ Court Record")
        dialogue_container = st.container(height=450, border=True)
        with dialogue_container:
            st.write("Review your gathered evidence below:")

            # Evidence emitted by the backend (e.g., from project.main)
            for ev in read_evidence_events(_runtime_log_path(), case_id=st.session_state.case_id):
                _render_evidence_card(ev["title"], ev["description"])

    with mid_col:
        st.header(" ")
        st.empty()

    with right_col:
        st.subheader("💬 Courtroom Dialogue")
        # Container keeps the history visually clean
        dialogue_container = st.container(height=450, border=True)
        with dialogue_container:
            backend_dialogue = read_dialogue_events(_runtime_log_path(), case_id=st.session_state.case_id)
            for line in (st.session_state.dialogue_history + backend_dialogue):
                if line["speaker"] == "Judge" or line["speaker"] == "judge":
                    st.markdown(f"👨‍⚖️ **{line['speaker']}:** *\"{line['text']}\"*")
                elif line["speaker"] == "Narrator" or line["speaker"] == "narrator":
                    st.markdown(f"🎙️ **{line['speaker']}:** *\"{line['text']}\"*")
                elif line["speaker"] == "Prosecutor" or line["speaker"] == "prosecutor":
                    st.markdown(f"🧣 **{line['speaker']}:** *\"{line['text']}\"*")
                elif line["speaker"] == "Witness" or line["speaker"] == "witness":
                    st.markdown(f"👩🏻‍🦰 **{line['speaker']}:** *\"{line['text']}\"*")
                else:
                    st.markdown(f"🔵 **{line['speaker']}:** *\"{line['text']}\"*")

with st.container(border=True):
    # 5. SENSEMAKING INTERFACE: PRESENTING THE K CANDIDATES
    st.subheader("💡 Make a choice")

    # Mock arguments simulating generation from Member 2
    # In Sprint 2, you'll use scikit-learn to cluster these dynamically!
    mock_candidates = [
        {"id": 1, "text": "Present the Autopsy Report to show the time of death.", "intent": "Evidence Check", "contradiction": False},
        {"id": 2, "text": "Present the Pocket Watch to prove the time of the struggle.", "intent": "Evidence Check", "contradiction": False},
        {"id": 3, "text": "Claim the defendant was at the movies (No alibi evidence exists).", "intent": "Bluffing", "contradiction": True},
        {"id": 4, "text": "Press the witness on what they were wearing that night.", "intent": "Cross-examination", "contradiction": False},
        {"id": 5, "text": "Argue that the dark courtroom environment made identification impossible.", "intent": "Cross-examination", "contradiction": False}
    ]

    backend_options_events = read_argument_options_events(_runtime_log_path(), case_id=st.session_state.case_id)
    backend_options = (backend_options_events[-1].get("options") if backend_options_events else None) or []

    candidates = backend_options if backend_options else mock_candidates
    if candidates is backend_options:
        st.caption("Options loaded from backend")

    # Display layout options using columns
    if candidates:
        cols = st.columns(len(candidates))
        for idx, col in enumerate(cols):
            candidate = candidates[idx]
            with col:
                # Visual styling block
                st.markdown(f"**Option {idx+1}**")
                st.caption(f"Intent: {candidate.get('intent', '')}")  # Grouping visualization placeholder

                text = str(candidate.get("text", ""))
                contradiction = bool(candidate.get("contradiction", False))

                # Sensemaking feature: Contrastive Highlighting (Turned ON/OFF via Bandit instructions)
                if contradiction:
                    st.error(text)
                else:
                    st.code(text, wrap_lines=True)

                # Unique key identifier prevents Streamlit from getting confused on clicks
                cid = candidate.get("id", idx + 1)
                if st.button("Present", key=f"btn_{cid}"):
                    log_telemetry("argument_selected", text)

                    # Update the game progression state
                    st.session_state.dialogue_history.append({"speaker": "Defense (You)", "text": text})

                    # Simple reactive response mechanism (Sprint 1 placeholder)
                    if contradiction:
                        st.session_state.dialogue_history.append({"speaker": "Judge", "text": "Order! That statement flies completely in the face of established reality!"})
                        log_telemetry("player_mistake", "Contradiction penalty triggered.")
                    else:
                        st.session_state.dialogue_history.append({"speaker": "Prosecutor", "text": "Objection! That argument is entirely trivial!"})

                    # Instantly refresh the UI state layout
                    st.rerun()

# 6. DEBUG FOOTER: TELEMETRY TRACKING (For Member 4 Integration)
st.divider()
with st.expander("🛠️ Live Backend Telemetry (Member 4 Pipeline Feed)"):
    if st.button("Reset app state", key="debug_reset_state"):
        reset_log_events(_runtime_log_path())
        st.session_state.clear()
        st.rerun()
    st.write(st.session_state.telemetry_log)