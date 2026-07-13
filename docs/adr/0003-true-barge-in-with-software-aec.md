# True barge-in interruption with software AEC

**Status:** accepted

HUGO must be interruptible mid-speech. We considered a keyword-only interrupt ("stop") versus true barge-in (any detected speech immediately halts playback). We chose true barge-in for a more natural conversational feel, which requires acoustic echo cancellation (AEC) on the mic input so HUGO's own speaker output isn't picked up by the mic and mistaken for a user interruption — the mic and speaker are physically close together on the Reachy Mini unit. AEC runs against the exact audio stream sent to the speaker, not just a generic noise filter.
