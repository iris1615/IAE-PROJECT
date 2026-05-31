import streamlit as st
import time

# Streamlit requires page configuration to be set before other UI calls.
st.set_page_config(page_title="Ace Attorney AI", layout="wide")

# 1. INITIALIZE GAME STATE
# We use st.session_state so data survives the top-to-bottom script re-runs.
if "game_step" not in st.session_state:
    st.session_state.game_step = 0
if "dialogue_history" not in st.session_state:
    st.session_state.dialogue_history = [
        {"speaker": "Judge", "text": "The court is now in session for the trial of... someone."}
    ]
if "telemetry_log" not in st.session_state:
    st.session_state.telemetry_log = []

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
        st.write("Review your gathered evidence below:")

        # Custom cards using standard Markdown
        st.info("**Autopsy Report**\n\nVictim passed away at precisely 10:00 PM due to blunt force trauma.")
        st.info("**Pocket Watch**\n\nFound at the scene. Completely shattered, hands stopped at 10:05 PM.")

    with mid_col:
        st.header(" ")
        st.empty()

    with right_col:
        st.subheader("💬 Courtroom Dialogue")

        # Container keeps the history visually clean
        dialogue_container = st.container(height=450, border=True)
        with dialogue_container:
            for line in st.session_state.dialogue_history:
                if line["speaker"] == "Judge":
                    st.markdown(f"👨‍⚖️ **{line['speaker']}:** *\"{line['text']}\"*")
                elif line["speaker"] == "Prosecutor":
                    st.markdown(f"🧣 **{line['speaker']}:** *\"{line['text']}\"*")
                else:
                    st.markdown(f"🔵 **{line['speaker']}:** *\"{line['text']}\"*")

with st.container(border=True):
    # 5. SENSEMAKING INTERFACE: PRESENTING THE K CANDIDATES
    st.subheader("💡 Select Your Argument (K=5)")

    # Mock arguments simulating generation from Member 2
    # In Sprint 2, you'll use scikit-learn to cluster these dynamically!
    mock_candidates = [
        {"id": 1, "text": "Present the Autopsy Report to show the time of death.", "intent": "Evidence Check", "contradiction": False},
        {"id": 2, "text": "Present the Pocket Watch to prove the time of the struggle.", "intent": "Evidence Check", "contradiction": False},
        {"id": 3, "text": "Claim the defendant was at the movies (No alibi evidence exists).", "intent": "Bluffing", "contradiction": True},
        {"id": 4, "text": "Press the witness on what they were wearing that night.", "intent": "Cross-examination", "contradiction": False},
        {"id": 5, "text": "Argue that the dark courtroom environment made identification impossible.", "intent": "Cross-examination", "contradiction": False}
    ]

    # Display layout options using columns
    cols = st.columns(len(mock_candidates))

for idx, col in enumerate(cols):
    candidate = mock_candidates[idx]
    with col:
        # Visual styling block
        st.markdown(f"**Option {idx+1}**")
        st.caption(f"Intent: {candidate['intent']}") # Grouping visualization placeholder
        
        # Sensemaking feature: Contrastive Highlighting (Turned ON/OFF via Bandit instructions)
        # For now, we manually simulate highlighting a contradiction in red
        if candidate["contradiction"]:
            st.error(candidate["text"]) 
        else:
            st.code(candidate["text"], wrap_lines=True)
            
        # Unique key identifier prevents Streamlit from getting confused on clicks
        if st.button("Present", key=f"btn_{candidate['id']}"):
            log_telemetry("argument_selected", candidate["text"])
            
            # Update the game progression state
            st.session_state.dialogue_history.append({"speaker": "Defense (You)", "text": candidate["text"]})
            
            # Simple reactive response mechanism (Sprint 1 placeholder)
            if candidate["contradiction"]:
                st.session_state.dialogue_history.append({"speaker": "Judge", "text": "Order! That statement flies completely in the face of established reality!"})
                log_telemetry("player_mistake", "Contradiction penalty triggered.")
            else:
                st.session_state.dialogue_history.append({"speaker": "Prosecutor", "text": "Objection! That argument is entirely trivial!"})
            
            # Instantly refresh the UI state layout
            st.rerun()

# 6. DEBUG FOOTER: TELEMETRY TRACKING (For Member 4 Integration)
st.divider()
with st.expander("🛠️ Live Backend Telemetry (Member 4 Pipeline Feed)"):
    st.write(st.session_state.telemetry_log)