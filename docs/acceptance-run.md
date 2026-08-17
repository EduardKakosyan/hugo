# Voice acceptance run

HUGO is a one-robot, one-user desk assistant: there is no analytics population to
read, so the honest success criterion is a **fixed script, spoken at conversational
volume from ~1m, run on the real robot** — once before the voice-quality work as a
baseline, and again after it. Voice character is judged by ear through the robot's
own speaker, never headphones (the Reachy Mini's USB audio device advertises exactly
one mode — 16kHz stereo S16_LE — so everything HUGO says is band-limited to 8kHz; a
voice that sounds rich on a laptop can turn to mud on the robot).

## The envelope being tested

A **normal speaking voice, 0.5–1m away, sitting at the desk.** Not leaning in, not
raised, not shouted. Anything further is a bonus, not a promise. Room-scale (2–3m)
pickup is explicitly out of scope — it needs beamforming the SDK doesn't expose.

## How to run it

One checkout runs at a time (one robot, one 121GB pool, one shared state dir):

```bash
scripts/dgx_worktree.sh sync
ssh hugo-dgx1 systemctl --user stop hugo
scripts/dgx_worktree.sh use
ssh hugo-dgx1 systemctl --user start hugo          # ~3-4 min today
ssh hugo-dgx1 journalctl --user -u hugo -f         # keep this open; it is the evidence
ssh hugo-dgx1 systemctl --user restart hugo-wake   # mandatory after any deploy
```

Record the journal alongside the tallies — `turn timing:` now carries `capture peak
… dBFS` and `peak wake score …`, and the `no speech within` line carries the capture
peak for exactly the turns that failed. Afterwards, `scripts/dgx_worktree.sh reset`
and confirm `free -g` shows no model memory held (ADR 0002).

Note which keys `~/.hugo_secrets` had set for the run. `HUGO_WAKE_WORD` in particular
is an **absolute path into the deployed `~/hugo` checkout**, so a worktree run still
loads the *deployed* copy of `hey_hugo.onnx`, not the branch's.

## Part A — wake word at conversational volume

Twenty separate attempts, spoken at normal volume from ~1m, with the robot idle (not
asleep) and at least a couple of seconds between attempts. Count an attempt as a hit
if HUGO chimes without you raising your voice or repeating yourself.

| Measure | Bar |
|---|---|
| Wake word fires at normal volume | **≥ 18 / 20** |

## Part B — the twenty-utterance conversation script

Spoken in order, in one sitting. "Expected" describes the behaviour this work is
building toward; on the **baseline** run several of these are expected to fail — that
is the point of taking a baseline.

| # | You say | Expected |
|---|---|---|
| 1 | "hey Hugo" (robot asleep) | chime + "on my way…", then conversational within ~35s |
| 2 | "hey Hugo" | chime, mic opens |
| 3 | "hi, how's it going" | a short spoken reply, one continuous phrase |
| 4 | "what time is it" | `get_current_time` → the correct local time, spoken |
| 5 | "remember I have a meeting at 1pm with DBS" | `remember_fact` → spoken acknowledgement |
| 6 | "what do you know about my meetings" | `recall_facts` → the fact from #5, spoken |
| 7 | "search for the weather in Halifax tomorrow" | `web_search` → a spoken summary |
| 8 | *(say nothing for a full window)* | **"Sorry, I didn't catch that"** out loud, mic reopens |
| 9 | "what did I just ask you to remember" | the fact from #5 — the retry cost no context |
| 10 | "tell me about the history of the octopus" | a long, multi-sentence reply — listen for gaps |
| 11 | *(interrupt #10 mid-reply by talking)* | HUGO stops within a beat and listens |
| 12 | "never mind, what's two plus two" | the interrupted reply is abandoned; "four" |
| 13 | *(pause ~10s mid-thought, then)* "what's the capital of Nova Scotia" | the window survived the pause; "Halifax" |
| 14 | "say that again" | same voice, same person, no drift |
| 15 | "remember my dentist appointment is on Thursday" | `remember_fact` → spoken acknowledgement |
| 16 | "what do you know about me" | `recall_facts` → both facts |
| 17 | "tell me a joke" | a reply with no laughter, no sing-song, no character |
| 18 | *(mumble)* "go to sleep" | **"Did you want me to go to sleep?"** — a question, never the action |
| 19 | "no" | conversation continues normally |
| 20 | "that's all" | end chime, conversation closes, HUGO stays awake |

### Bars

| What we measure | Bar to pass |
|---|---|
| Wake word fires at normal volume (Part A) | ≥ 18 / 20 attempts |
| Utterances needing a repeat because HUGO misheard | 0 |
| Command utterances producing the right tool call (#4–7, 15, 16) | every one |
| **Silent turns** — HUGO does nothing and says nothing | **0, unconditionally** |
| Barge-in mid-reply (#11) | interrupts reliably |

**Zero silent turns is the headline number.** Silence is the worst failure mode
because it is unattributable: from where you're sitting you cannot tell whether HUGO
misheard, chose not to act, or crashed. A wrong answer, or an audible "I didn't catch
that", is strictly better than nothing.

### By ear, every run

- **Continuity** — a reply arrives as one continuous phrase, with no audible holes
  between sentences.
- **Consistency** — HUGO sounds like the same person on every turn. It never laughs,
  never goes sing-song, never drifts into a character.
- **Clarity** — loud syllables don't slam into distortion; quiet ones stay audible.

## Results

Copy the block below per run. Do not summarise away a failure — the journal lines
for a failed turn are the most useful thing a run produces.

```
Date / sha / checkout:
Secrets keys set:
Part A wake word:            __ / 20
Repeats needed:              __
Correct tool calls:          __ / 6
Silent turns:                __        (bar: 0)
Barge-in (#11):              pass / fail
Continuity (by ear):
Consistency (by ear):
Clarity (by ear):
Journal notes (capture peak dBFS range, wake scores, failures):
```

### Baseline — pre-work (Phase 1)

*To be filled in on the hardware session: run against this branch with only the
Phase 1 metering in place, so the numbers describe today's behaviour. Expect
failures at #8 (silence, no retry line yet), #11 (barge-in is wake-word-gated),
#13 (6s follow-up window), and #18 (sleep is matched by exact string and executes
without confirming).*

```
Date / sha / checkout:       TBD
Secrets keys set:            TBD
Part A wake word:            TBD
Repeats needed:              TBD
Correct tool calls:          TBD
Silent turns:                TBD
Barge-in (#11):              TBD
Continuity (by ear):         TBD
Consistency (by ear):        TBD
Clarity (by ear):            TBD
Journal notes:               TBD
```

### After — post-implementation (Phase 9)

```
Date / sha / checkout:       TBD
```
