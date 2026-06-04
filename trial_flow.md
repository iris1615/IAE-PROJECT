
# Courtroom Narrative Flow & Architecture

## 1. Narrative Flows

### Usual Ace Attorney Narrative Flow

Intro → Investigation → Trial Day (Witness Intro → Testimony → Cross Examination [Press / Present Evidence / Contradiction]) → Judge Evaluation → Narrative Twist → Verdict

### Implemented Narrative Flow for This Project

Our flow has been adapted to support non-linear, interactive terminal navigation managed by a live state machine:

INTRO
  ↓
TESTIMONY (Initial bloc presentation of all witness statements)
  ↓
CROSS_EXAMINATION (Free-navigation loop between statements using [A/D])
  ├── [1] Press Witness ──> (Dynamic Defense prompt generation + Stress-based Witness reaction 0-10)
  ├── [2] Brainstorm Strategy ──> (Consult the AI Team / Grounded Argument Verification)
  └── [3] Present Evidence ──> (Symbolic Contradiction Check)
  ↓
OBJECTION / CONTRADICTION (Triggered instantly when evidence perfectly matches the statement)
  ↓
FINAL DEFENSE: CLOSING ARGUMENT (Triggered at 100% progress, strictly locked to discovered truths)
  ↓
VERDICT (The Judge's decision based on the successful outcome of the contradictions)

> ⚠️ **STRICT GUARDRAIL:** The LLM cannot create or invent facts outside the truth layer (`truth.json` or the dynamic discovered facts bundle of each case). Absolutely no random crimes (e.g., gruesome murders) can bleed into minor, specific cases (e.g., Monopoly money forgery).

---

## 2. Implemented Runtime Architecture

```text
       [ CASE JSON / WITNESS JSON ] (Rich profiles, Hidden secrets, Behavior rules)
                   ↓
       [ TRIAL STATE MACHINE ] (Manages Phases, Witness Stress, Verdict Progress)
                   ↓
       [ CURRENT CONTEXT ] (Active Statement, Current Stress Level)
                   ↓
       [ RAG RETRIEVAL ] (Semantic search/Chroma mapping of case clues and rules)
                   ↓
       [ CHARACTER PROMPTING ] (Profile injection, Style/Dialect hooks, Anti-Hallucination rules)
                   ↓
   ┌───────────────┴───────────────┐
   ↓                               ↓
[K ARGUMENT GENERATION]   [DYNAMIC PRESS GENERATION] (Defense Attorney line + Stress Reaction)
   ↓                               ↓
[SYMBOLIC VERIFIER]                │
(Validates Cues and Facts)         │
   ↓                               ↓
   └───────────────┬───────────────┘
                   ↓
            [PLAYER CHOICE] (Interactive Menu: Press, Brainstorm, Present)
                   ↓
          [NARRATIVE UPDATE] (State transitions, Stress 6+ Revelations, Closing Speech)
```
