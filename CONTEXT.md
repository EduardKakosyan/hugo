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
