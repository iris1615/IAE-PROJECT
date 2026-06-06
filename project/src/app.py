import streamlit as st
import time
import sys
from pathlib import Path
from streamlit_autorefresh import st_autorefresh
from PIL import Image


# When running `streamlit run project/src/app.py`, Streamlit adds `project/src` to sys.path.
# Ensure the repo root is also on sys.path so `import project...` resolves correctly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
    
from project.common.log_events import read_argument_options_events, read_dialogue_events, read_evidence_events, read_statement_events ,log_input, reset_log_events, log_user_info

# Streamlit requires page configuration to be set before other UI calls.
st.set_page_config(page_title="Ace Attorney AI", layout="wide")

st_autorefresh(interval=1000, key="timed_refresh")


def _repo_root() -> Path:
    # project/src/app.py -> parents[2] is repo root
    return Path(__file__).resolve().parents[2]

# 1. INITIALIZE GAME STATE
# We use st.session_state so data survives the top-to-bottom script re-runs.
if "game_step" not in st.session_state:
    st.session_state.game_step = 0
if "dialogue_history" not in st.session_state:
    st.session_state.dialogue_history = []
if "telemetry_log" not in st.session_state:
    st.session_state.telemetry_log = []
if "courtroom_image" not in st.session_state:
    st.session_state.courtroom_image = str(_repo_root() / "project" / "assets" / "courtroom.png")
if "caption" not in st.session_state:
    st.session_state.caption = "Welcome to the courtroom! Awaiting the judge's opening statement."

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

def set_image(path, caption):
    st.session_state.courtroom_image = path
    st.session_state.caption = caption

def overlay_images(bottom_path, top_path):
    # Open both images
    bottom_img = Image.open(bottom_path).convert("RGBA")
    top_img = Image.open(top_path).convert("RGBA")
    
    # Resize top image to perfectly match the bottom image size if they differ
    top_img = top_img.resize(bottom_img.size)
    
    # Paste the top image directly over the bottom image 
    # (The second top_img acts as a transparency mask so alpha channels work!)
    combined_img = Image.alpha_composite(bottom_img, top_img)
    
    return combined_img

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
            for ev in read_evidence_events(_runtime_log_path()):
                _render_evidence_card(ev["title"], ev["description"])

    with mid_col:
        st.image(st.session_state.courtroom_image, caption=st.session_state.caption, use_column_width=True)
    
    with right_col:
        st.subheader("💬 Courtroom Dialogue")
        # Container keeps the history visually clean
        dialogue_container = st.container(height=450, border=True, autoscroll=True)
        with dialogue_container:
            backend_dialogue = read_dialogue_events(_runtime_log_path())
            for line in (st.session_state.dialogue_history + backend_dialogue):
                if "JUDGE JUDY" in line["speaker"].upper():
                    st.markdown(f"👨‍⚖️ **{line['speaker']}:** *\"{line['text']}\"*")
                    set_image(str(_repo_root() / "project" / "assets" / "judge.png"), f"👨‍⚖️ **{line['speaker']}:** *\"{line['text']}\"*")
                elif "NARRATOR" in line["speaker"].upper():
                    st.markdown(f"🎙️ **{line['speaker']}:** *\"{line['text']}\"*")
                    set_image(str(_repo_root() / "project" / "assets" / "courtroom.png"), f"🎙️ **{line['speaker']}:** *\"{line['text']}\"*")
                elif "LUCIEN VALEN" in line["speaker"].upper() or "PROSECUTOR" in line["speaker"].upper():
                    st.markdown(f"🧣 **{line['speaker']}:** *\"{line['text']}\"*")
                    if "OBJECTION" in line['text'].upper():
                        set_image(overlay_images(str(_repo_root() / "project" / "assets" / "prosecutor.png"), str(_repo_root() / "project" / "assets" / "objection.png")), f"🧣 **{line['speaker']}:** *\"{line['text']}\"*")
                    else:
                        set_image(str(_repo_root() / "project" / "assets" / "prosecutor.png"), f"🧣 **{line['speaker']}:** *\"{line['text']}\"*")
                elif "CONNOR ROSE[YOU]" in line["speaker"].upper():
                    st.markdown(f"🔵 **{line['speaker']}:** *\"{line['text']}\"*")
                    if "Hold it!" in line['text']:
                        set_image(overlay_images(str(_repo_root() / "project" / "assets" / "player.png"), str(_repo_root() / "project" / "assets" / "holdit.png")), f"🔵 **{line['speaker']}:** *\"{line['text']}\"*")
                    else:
                        set_image(str(_repo_root() / "project" / "assets" / "player.png"), f"🔵 **{line['speaker']}:** *\"{line['text']}\"*")
                else:
                    if "SHANE" in line["speaker"].upper():
                        st.markdown(f"👩🏻‍🦰 **{line['speaker']}:** *\"{line['text']}\"*")
                        set_image(str(_repo_root() / "project" / "assets" / "witness.png"), f"👩🏻‍🦰 **{line['speaker']}:** *\"{line['text']}\"*")  
                    else:
                        st.markdown(f"👨‍🦰 **{line['speaker']}:** *\"{line['text']}\"*")
                        set_image(str(_repo_root() / "project" / "assets" / "witness2.png"), f"👨‍🦰 **{line['speaker']}:** *\"{line['text']}\"*")
                    

with st.container(border=True):
    # 5. SENSEMAKING INTERFACE: PRESENTING THE K CANDIDATES
    st.subheader("💡 Make a choice")

    backend_options_events = read_argument_options_events(_runtime_log_path())
    backend_options = (backend_options_events[-1].get("options") if backend_options_events else None) or []

    candidates = backend_options
    statement = read_statement_events(_runtime_log_path())
    if statement:
        st.markdown(f"**Current Statement:** {statement[-1]['text']}")

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
                    log_user_info(
                        log_file=_repo_root() / "project" / "logs" / "user_info.json",
                        time_stamp=time.time(),
                        action="argument_option_selection",
                        detail=f"Selected option: {cid} - {text}",
                        source="app.py"
                    )
                    log_input(
                        log_file= _repo_root() / "project" / "logs" / "input.jsonl", 
                        input_type="argument_option_selection",
                        input_value=cid, 
                        source="app.py"
                    )
                    print(f"User selected option {cid}: {text}")

                    # Instantly refresh the UI state layout
                    st.rerun()

# 6. DEBUG FOOTER: TELEMETRY TRACKING (For Member 4 Integration)
st.divider()
with st.expander("🛠️ Live Backend Telemetry (Member 4 Pipeline Feed)"):
    if st.button("Reset app state", key="debug_reset_state"):
        reset_log_events(_runtime_log_path())
        reset_log_events(_repo_root() / "project" / "logs" / "input.jsonl")
        st.session_state.clear()
        st.rerun()
    if st.button("Clear Telemetry Data", key="debug_clear_telemetry"):
        reset_log_events(_repo_root() / "project" / "logs" / "user_info.json")
    st.write(st.session_state.telemetry_log)