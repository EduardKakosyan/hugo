# True barge-in interruption with software AEC

**Status:** accepted (amended 2026-07-23: wake-word interrupt until AEC exists)

HUGO must be interruptible mid-speech. We considered a keyword-only interrupt ("stop") versus true barge-in (any detected speech immediately halts playback). We chose true barge-in for a more natural conversational feel, which requires acoustic echo cancellation (AEC) on the mic input so HUGO's own speaker output isn't picked up by the mic and mistaken for a user interruption — the mic and speaker are physically close together on the Reachy Mini unit. AEC runs against the exact audio stream sent to the speaker, not just a generic noise filter.

**Amendment (2026-07-23):** True barge-in shipped before the AEC composite existed, and live sessions confirmed the predicted failure: HUGO's own speech trips the barge-in VAD, playback cuts, and the loop re-enters LISTENING off its own voice — conversations never terminate. Until software AEC is built and verified on hardware, interruption while HUGO is speaking is wake-word-gated (the wake word interrupts playback; arbitrary speech does not). openWakeWord is robust to HUGO's own voice in a way bare VAD is not. True barge-in remains the end state; this amendment sequences it strictly after AEC, rather than tuning VAD thresholds on a mechanism that is structurally broken without echo cancellation.
