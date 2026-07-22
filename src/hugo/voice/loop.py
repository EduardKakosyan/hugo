"""The core voice loop state machine: IDLE -> LISTENING -> THINKING ->
SPEAKING -> (LISTENING | IDLE), with true barge-in (docs/adr/0003).

Every dependency is a Protocol, so the state machine and its cancellation
logic are unit-tested against fully scripted fakes — no hardware, no real
model inference needed (see tests/unit/voice/test_loop.py). This is
deliberate: barge-in correctness is the hardest, highest-value thing to
prove here, and it's provable without any of that.

Uses FrameBroadcaster (broadcaster.py) rather than sharing the robot's raw
mic generator directly across states — this turned out not to be optional.
Each state's mic-consuming coroutine runs as its own asyncio.Task and gets
cancelled in the non-interrupting case (e.g. SPEAKING's barge-in watcher,
once playback finishes normally); cancelling a task while it's mid-`async
for` over a *shared* generator closes/poisons that generator, breaking
consumption for every subsequent state (observed directly: it manifested
as a tight, 100%-CPU busy loop in _run_idle, not a hang — an exhausted
generator's `async for` returns instantly forever). Each state instead
gets its own broadcaster.subscribe() — cancelling one subscriber doesn't
touch the underlying pump or any other subscriber.

Two things added after real dgx1 testing surfaced them: _run_idle plays a
short confirmation chime (voice/chime.py) the instant the wake word fires,
since without it there's no way to tell "not hearing me" apart from
"heard me, then something downstream broke silently" -- which is exactly
what the second addition fixes. An uncaught exception in *any* state
handler propagates out of run()'s while loop uncaught, silently killing
its asyncio.Task with no log line -- confirmed twice on dgx1, in two
different states: a real 400 from vLLM (tool-calling not enabled
server-side -- see orchestrator.py's _build_specs) from THINKING, and
the chime playback freeze in IDLE right after wake word detection.
run() now wraps every dispatch in one catch-all that logs and recovers
to IDLE, rather than patching each state individually as the next one
turns up broken.

The chime freeze itself (two real dgx1 hangs, 2026-07-16 00:45 and
14:10) turned out not to be an exception at all: stop_playing() on
reachy_mini's local backend sets the SINGLE shared capture+playback
gstreamer pipeline to NULL, which with capture live either deadlocks in
set_state or returns leaving the mic permanently dead (both reproduced
in isolation on real hardware, 2026-07-22). The catch-all can't help
with a blocked await, so the real fix is structural: run() owns
start_playing exactly once at startup, playback anywhere else is a bare
play_audio push, and barge-in flushes queued audio via clear_playback()
-- no state handler ever touches pipeline state. See run() and
robot/audio_io.py's clear_playback docstring.

AEC is NOT wired in directly here. `SpeechDetector.feed()` is handed
whatever mic frames the caller provides — during real wiring (M1.11), the
concrete SpeechDetector used for barge-in should be a small composite that
runs AEC (see voice/aec.py) against the mic frame before calling the real
Silero VAD, using the TTS chunk most recently sent to the speaker as the
reference. That composite isn't built yet: TTS outputs 24kHz (see
qwen_tts_synthesizer.py) while AEC/VAD expect 16kHz, so it needs
resampling, and the exact frame-size alignment is easier to get right with
a real robot's actual mic frame sizes in hand than to guess now. Keeping
VoiceLoop itself agnostic to AEC means this can be added later without
touching the state machine.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Literal, Protocol

from hugo.robot.audio_io import RobotAudioIO
from hugo.voice.broadcaster import FrameBroadcaster
from hugo.voice.chime import wake_chime_pcm16
from hugo.voice.resample import LinearPcm16Resampler
from hugo.voice.stt import Transcript
from hugo.voice.turn import Turn
from hugo.voice.vad import SpeechEvent

logger = logging.getLogger(__name__)

State = Literal["IDLE", "LISTENING", "THINKING", "SPEAKING"]


class WakeWordListener(Protocol):
    last_score: float

    def feed(self, pcm16_chunk: bytes) -> bool: ...
    def reset(self) -> None: ...


class SpeechDetector(Protocol):
    def feed(self, pcm16_chunk: bytes) -> SpeechEvent | None: ...
    def reset(self) -> None: ...


class SttSession(Protocol):
    async def send_audio(self, pcm16_chunk: bytes) -> None: ...
    async def end_utterance(self) -> None: ...
    def transcripts(self) -> AsyncIterator[Transcript]: ...


class TtsSession(Protocol):
    def speak(self, text: str) -> AsyncIterator[bytes]: ...
    async def cancel(self) -> None: ...


class Thinker(Protocol):
    async def think(self, user_text: str) -> str: ...


class VoiceLoop:
    def __init__(
        self,
        robot: RobotAudioIO,
        wake_word: WakeWordListener,
        vad: SpeechDetector,
        stt: SttSession,
        tts: TtsSession,
        thinker: Thinker,
        tts_sample_rate_hz: int = 24_000,
    ) -> None:
        self._robot = robot
        self._wake_word = wake_word
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._thinker = thinker
        # TTS chunks arrive at the synthesizer's native rate, the speaker
        # runs at the robot's — _run_speaking resamples between them (see
        # voice/resample.py for the real-hardware mismatch this fixes).
        self._tts_sample_rate_hz = tts_sample_rate_hz
        self.state: State = "IDLE"
        self._pending_transcript: str = ""
        self._pending_response: str = ""

    async def run(self) -> None:
        await self._robot.start_recording()
        # start_playing exactly once, up front, and never stop_playing
        # until shutdown: reachy_mini's local backend runs capture and
        # playback in ONE gstreamer pipeline (shared clock for AEC), and
        # stop_playing() sets that whole pipeline to NULL. Called mid-loop
        # with capture live it either deadlocks in set_state (both real
        # dgx1 freezes on 2026-07-16, right after wake-word chime
        # playback) or returns with the mic permanently dead (0 frames
        # after, reproduced in isolation on 2026-07-22). Playback between
        # utterances is just push_audio_sample; barge-in flushes with
        # clear_playback() instead of stopping the pipeline.
        await self._robot.start_playing()
        broadcaster = FrameBroadcaster(self._robot.read_mic_frames())
        broadcaster.start()
        try:
            while True:
                try:
                    await self._dispatch(broadcaster)
                except Exception:
                    # Same reasoning as _run_thinking's own catch (see the
                    # module docstring's incident writeup), generalized to
                    # every state: real hardware failure found live on
                    # dgx1 in a *different* state (IDLE, playing the wake
                    # chime) than the one already hardened -- a single
                    # narrow catch wasn't enough. Any state handler dying
                    # must recover to IDLE, not silently kill this task.
                    logger.exception("unhandled error in %s state, recovering to IDLE", self.state)
                    self.state = "IDLE"
        finally:
            await broadcaster.stop()
            await self._robot.stop_recording()

    async def _dispatch(self, broadcaster: FrameBroadcaster) -> None:
        if self.state == "IDLE":
            await self._run_idle(broadcaster)
        elif self.state == "LISTENING":
            transcript = await self._run_listening(broadcaster)
            if transcript:
                self._pending_transcript = transcript
                self.state = "THINKING"
            else:
                self.state = "IDLE"
        elif self.state == "THINKING":
            response = await self._run_thinking(self._pending_transcript)
            self._pending_response = response
            self.state = "SPEAKING"
        elif self.state == "SPEAKING":
            interrupted = await self._run_speaking(self._pending_response, broadcaster)
            self.state = "LISTENING" if interrupted else "IDLE"

    # Throttled diagnostic logging added live on dgx1 to answer a question
    # `hugo dev wake` couldn't: that tool proved detection works, but only
    # ever run with vLLM/STT/TTS stopped (idle machine) -- it says nothing
    # about whether IDLE even sees frames, or what scores look like, once
    # those are all competing for the same CPU/GPU during a real `hugo
    # start` session. Every ~1s (100 frames @ ~10ms/frame) rather than
    # per-frame, so this doesn't flood the log on its own.
    _IDLE_LOG_EVERY_N_FRAMES = 100

    async def _run_idle(self, broadcaster: FrameBroadcaster) -> None:
        self._wake_word.reset()
        frame_count = 0
        async for frame in broadcaster.subscribe():
            frame_count += 1
            if frame_count % self._IDLE_LOG_EVERY_N_FRAMES == 0:
                logger.info(
                    "IDLE: %d frames seen, last wake-word score=%.3f",
                    frame_count,
                    self._wake_word.last_score,
                )
            if self._wake_word.feed(frame):
                logger.info("wake word detected after %d frames", frame_count)
                await self._play_wake_chime()
                self.state = "LISTENING"
                return

    async def _play_wake_chime(self) -> None:
        await self._robot.play_audio(wake_chime_pcm16(self._robot.output_sample_rate_hz))

    async def _run_listening(self, broadcaster: FrameBroadcaster) -> str | None:
        self._vad.reset()
        mic = broadcaster.subscribe()
        final_text: str | None = None

        async def collect_transcripts() -> None:
            nonlocal final_text
            async for t in self._stt.transcripts():
                if t.kind == "final":
                    final_text = t.text

        async def feed_audio_until_speech_ends() -> None:
            async for frame in mic:
                await self._stt.send_audio(frame)
                if self._vad.feed(frame) == "speech_end":
                    await self._stt.end_utterance()
                    return

        turn = Turn()
        transcript_task = turn.spawn(collect_transcripts())
        feed_task = turn.spawn(feed_audio_until_speech_ends())
        await feed_task
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(transcript_task, timeout=5.0)
        await turn.cancel_all()
        return final_text

    async def _run_thinking(self, user_text: str) -> str:
        # Broad except is deliberate: Thinker is a swappable Protocol, and
        # this is the system boundary that isolates the state machine from
        # whatever it can fail with (network, model, parsing errors) -- see
        # the module docstring for the real incident that motivated this.
        try:
            return await self._thinker.think(user_text)
        except Exception:
            logger.exception("thinker failed to produce a response")
            return "Sorry, I ran into a problem thinking about that."

    async def _run_speaking(self, text: str, broadcaster: FrameBroadcaster) -> bool:
        """Returns True if barge-in interrupted playback (caller should go
        straight to LISTENING to capture what the user just said)."""
        self._vad.reset()
        mic = broadcaster.subscribe()
        turn = Turn()
        barge_in_event = asyncio.Event()

        async def play() -> None:
            resampler = LinearPcm16Resampler(
                self._tts_sample_rate_hz, self._robot.output_sample_rate_hz
            )
            async for chunk in self._tts.speak(text):
                resampled = resampler.process(chunk)
                if resampled:
                    await self._robot.play_audio(resampled)

        async def watch_for_barge_in() -> None:
            async for frame in mic:
                if self._vad.feed(frame) == "speech_start":
                    barge_in_event.set()
                    return

        playback_task = turn.spawn(play())
        watch_task = turn.spawn(watch_for_barge_in())

        done, _pending = await asyncio.wait(
            {playback_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
        )

        interrupted = watch_task in done and barge_in_event.is_set()
        if interrupted:
            await self._tts.cancel()
            # Cancelling TTS stops *generating* audio, but chunks already
            # pushed sit in the speaker queue and would keep playing over
            # the user — flush them. clear_playback (not stop_playing,
            # which kills the shared capture pipeline — see run()).
            await self._robot.clear_playback()
        await turn.cancel_all()
        return interrupted
