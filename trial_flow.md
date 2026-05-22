**Usual Ace Attorney narrative flow**

Intro
→ Investigation
→ Trial Day
    → Witness Introduction
    → Testimony
    → Cross Examination
        → Press
        → Present Evidence
        → Contradiction
    → Judge Evaluation
    → Narrative Twist
→ Verdict

**Narrative flow for this project**
INTRO
INVESTIGATION
TESTIMONY
CROSS_EXAMINATION
OBJECTION
VERDICT

The LLM can't create facts outside the truth layer (truth.json of each case)

**Reccomended runtime architecture**

CASE JSON
    ↓
TRIAL STATE MACHINE
    ↓
CURRENT CONTEXT
    ↓
RAG RETRIEVAL
    ↓
CHARACTER PROMPTING
    ↓
K ARGUMENT GENERATION
    ↓
VERIFIER
    ↓
PLAYER CHOICE
    ↓
NARRATIVE UPDATE