# HUGO

A voice-first, embodied personal assistant that lives on local compute (a DGX Spark-class machine) and controls a Reachy Mini robot for physical presence, vision, and speech.

## Language

**Local compute**:
Running HUGO's core reasoning, speech, and vision models on hardware you own (the DGX Spark), with no cloud LLM provider in the loop for the "brain." Tools that call inherently cloud-hosted services (Outlook/Graph API, web search) still reach out over the network — "local compute" describes where inference happens, not a ban on all network calls.
_Avoid_: "Offline", "airgapped" — HUGO is not designed to work without network access, since tool calls depend on it.

**Barge-in**:
The user interrupting HUGO by speaking while it is currently talking, causing it to immediately stop playback and listen. Triggered by any detected speech (not a specific keyword).
_Avoid_: "Interrupt" alone (ambiguous with task cancellation via tool errors, etc.)

**Wake word**:
The activation phrase ("Hey HUGO" or similar) required before HUGO treats detected speech as a request directed at it, while idle.

**Conversation**:
Everything between a wake-word activation and HUGO returning to idle: one or more turns. A conversation ends by stop phrase, by the follow-up window expiring with no speech, or by HUGO being put to sleep.
_Avoid_: "Session" (overloaded with process lifecycle)

**Follow-up window**:
The short period (~6 seconds) after HUGO finishes a reply during which the mic stays open and the user can speak again without repeating the wake word. Expiry ends the conversation with an audible cue.

**Acknowledgment**:
A short spoken confirmation, delivered the moment HUGO commits to a slow action, naming what it's about to do ("let me search for that"). Followed by brief progress updates if the work runs long. Distinct from the reply — it promises one, it isn't one.
_Avoid_: "Filler" (the acknowledgment carries information; it isn't dead air)

**Stop phrase**:
An exact spoken phrase ("stop", "that's all", "never mind") that ends the conversation immediately. HUGO stays awake: models remain loaded and the wake word still works. Matched deterministically on the transcript — never interpreted by the LLM.

**Sleep**:
Full shutdown, voice-triggered ("go to sleep") or via CLI: every model process terminates, all model memory is released to the shared machine, the robot moves to its rest posture, and the conversation history is gone. Persistent facts survive sleep. Waking again is a cold `hugo start`.
_Avoid_: "Stop" (that's the conversation-level command), "shutdown" (ambiguous with host shutdown)

**Reasoning trace**:
The private thinking text a reasoning-capable model emits before its actual answer. Never spoken aloud and never shown to the user — HUGO's replies are only the final answer. (HUGO v1 runs with reasoning disabled by default; if it is ever enabled, the trace must be separated from the reply server-side, not filtered by the client.)
