"""The core voice loop state machine: IDLE -> LISTENING -> RESPONDING ->
(LISTENING | IDLE), with conversation lifecycle per VEN-56.

Every dependency is a Protocol, so the state machine and its cancellation
logic are unit-tested against fully scripted fakes — no hardware, no real
model inference needed (see tests/unit/voice/test_loop.py).

VEN-56 replaced the old THINKING/SPEAKING pair with one RESPONDING state:
the Thinker is now an async generator of utterances, so speech overlaps
generation (the old shape waited for the complete LLM answer before the
first TTS sample — 40+ seconds of dead air measured live on dgx1). While
RESPONDING, a producer task drains the thinker into a queue and a speaker
task plays each utterance; a gap watchdog speaks a canned "still working"
nudge when nothing has reached the speaker for a while (covers slow tool
calls AND a slow LLM pass with one mechanism).

Interruption while RESPONDING is wake-word-gated, not VAD-gated: ADR 0003
(amended 2026-07-23) — without AEC, HUGO's own speaker output trips a bare
VAD and the loop re-enters LISTENING off its own voice, so conversations
never terminate. True barge-in returns once the AEC composite exists.

A conversation (CONTEXT.md) ends by stop phrase, by the follow-up window
expiring with no speech, by an empty transcript, or by the sleep phrase —
which also ends the whole session via on_sleep (orchestrator shutdown:
models unload, robot rests). Stop/sleep phrases are matched
deterministically on the transcript, never LLM-interpreted: an accidental
sleep costs a minutes-long model reload.

Uses FrameBroadcaster (broadcaster.py) rather than sharing the robot's raw
mic generator directly across states — this turned out not to be optional.
Each state's mic-consuming coroutine runs as its own asyncio.Task and gets
cancelled in the non-interrupting case; cancelling a task while it's
mid-`async for` over a *shared* generator closes/poisons that generator,
breaking consumption for every subsequent state (observed directly: a
tight, 100%-CPU busy loop in _run_idle). Each state instead gets its own
broadcaster.subscribe().

Hard-won pipeline discipline (two real dgx1 freezes, 2026-07-16, both
reproduced in isolation 2026-07-22): run() owns start_playing exactly once
at startup and never stops the pipeline mid-loop — reachy_mini's local
backend runs capture and playback in ONE gstreamer pipeline, and
stop_playing() with capture live either deadlocks in set_state or returns
leaving the mic permanently dead. Playback anywhere else is a bare
play_audio push; interruption flushes queued audio via clear_playback().

run() wraps every dispatch in one catch-all that logs and recovers to
IDLE — an uncaught exception in any state handler otherwise silently kills
the loop's asyncio.Task with no log line (confirmed twice on dgx1, in two
different states).

Playback is queue-based: play_audio returns when a chunk is *queued*, not
played. The loop tracks an estimated playback deadline (sum of pushed chunk
durations) and waits it out before opening the follow-up window — without
this, the open mic hears the tail of HUGO's own reply (no AEC) and
transcribes it as a bogus follow-up turn.
"""

import asyncio
import contextlib
import logging
import re
from collections import deque
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Literal, Protocol

from hugo.robot.audio_io import RobotAudioIO
from hugo.voice.broadcaster import FrameBroadcaster
from hugo.voice.chime import conversation_end_chime_pcm16, wake_chime_pcm16
from hugo.voice.resample import StreamingPcm16Resampler
from hugo.voice.stt import Transcript
from hugo.voice.turn import Turn
from hugo.voice.vad import SpeechEvent

logger = logging.getLogger(__name__)

State = Literal["IDLE", "LISTENING", "RESPONDING"]

# Deterministic conversation commands (CONTEXT.md: Stop phrase, Sleep).
# Matched against the normalized whole transcript — "stop the timer" is a
# request, "stop" is a command.
STOP_PHRASES = ("stop", "that's all", "thats all", "that is all", "never mind", "nevermind")
SLEEP_PHRASES = ("go to sleep",)
SLEEP_CONFIRMATION = "Going to sleep."
PROGRESS_NUDGE = "Still working on it."
THINKER_FAILURE_APOLOGY = "Sorry, I ran into a problem thinking about that."


def normalize_command(text: str) -> str:
    """Lowercases and strips everything but letters/apostrophes so STT
    punctuation ("Stop.") can't defeat an exact phrase match."""
    cleaned = re.sub(r"[^a-z']+", " ", text.lower())
    return " ".join(cleaned.split())


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
    def think(self, user_text: str) -> AsyncIterator[str]:
        """Yields utterances to speak, in order, as the response forms."""
        ...


class VoiceLoop:
    # ~0.5s of ~10ms mic frames kept while waiting for speech onset, then
    # handed to STT so VAD trigger latency doesn't clip the first syllable.
    _PRE_ROLL_MAX_FRAMES = 50

    def __init__(
        self,
        robot: RobotAudioIO,
        wake_word: WakeWordListener,
        vad: SpeechDetector,
        stt: SttSession,
        tts: TtsSession,
        thinker: Thinker,
        tts_sample_rate_hz: int = 24_000,
        no_speech_timeout_s: float = 8.0,
        follow_up_window_s: float = 6.0,
        max_utterance_s: float = 30.0,
        progress_update_after_s: float = 8.0,
        stop_phrases: Sequence[str] = STOP_PHRASES,
        sleep_phrases: Sequence[str] = SLEEP_PHRASES,
        on_sleep: Callable[[], None] | None = None,
    ) -> None:
        self._robot = robot
        self._wake_word = wake_word
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._thinker = thinker
        # TTS chunks arrive at the synthesizer's native rate, the speaker
        # runs at the robot's — _speak resamples between them (see
        # voice/resample.py for the real-hardware mismatch this fixes).
        self._tts_sample_rate_hz = tts_sample_rate_hz
        self._no_speech_timeout_s = no_speech_timeout_s
        self._follow_up_window_s = follow_up_window_s
        self._max_utterance_s = max_utterance_s
        self._progress_update_after_s = progress_update_after_s
        self._stop_phrases = frozenset(normalize_command(p) for p in stop_phrases)
        self._sleep_phrases = frozenset(normalize_command(p) for p in sleep_phrases)
        self._on_sleep = on_sleep

        self.state: State = "IDLE"
        self._pending_transcript: str = ""
        self._listening_is_follow_up = False
        self._sleep_requested = False
        # Playback bookkeeping (see module docstring on queue-based playback).
        self._playback_deadline = 0.0
        self._last_audio_pushed_at = 0.0
        # Per-turn latency instrumentation (VEN-56: measured, logged per turn).
        self._end_of_speech_at: float | None = None
        self._transcript_at: float | None = None
        self._first_audio_at: float | None = None

    async def run(self) -> None:
        await self._robot.start_recording()
        # start_playing exactly once, up front, and never stop_playing
        # until shutdown — see the module docstring's pipeline-discipline
        # writeup (two real dgx1 freezes).
        await self._robot.start_playing()
        broadcaster = FrameBroadcaster(self._robot.read_mic_frames())
        broadcaster.start()
        try:
            while not self._sleep_requested:
                try:
                    await self._dispatch(broadcaster)
                except Exception:
                    # Any state handler dying must recover to IDLE, not
                    # silently kill this task — see the module docstring.
                    logger.exception("unhandled error in %s state, recovering to IDLE", self.state)
                    self.state = "IDLE"
        finally:
            await broadcaster.stop()
            await self._robot.stop_recording()

    async def _dispatch(self, broadcaster: FrameBroadcaster) -> None:
        if self.state == "IDLE":
            await self._run_idle(broadcaster)
            await self._play(wake_chime_pcm16(self._robot.output_sample_rate_hz))
            self._listening_is_follow_up = False
            self.state = "LISTENING"
        elif self.state == "LISTENING":
            transcript = await self._run_listening(broadcaster)
            await self._route_transcript(transcript)
        elif self.state == "RESPONDING":
            interrupted = await self._run_responding(self._pending_transcript, broadcaster)
            if interrupted:
                # The user said the wake word to cut HUGO off — same audible
                # confirmation as a fresh wake, then a full listening window.
                await self._play(wake_chime_pcm16(self._robot.output_sample_rate_hz))
                self._listening_is_follow_up = False
            else:
                self._listening_is_follow_up = True
            self.state = "LISTENING"

    async def _route_transcript(self, transcript: str | None) -> None:
        if transcript is None or not transcript.strip():
            await self._end_conversation()
            return
        command = normalize_command(transcript)
        if command in self._sleep_phrases:
            await self._run_sleep()
            return
        if command in self._stop_phrases:
            await self._end_conversation()
            return
        self._pending_transcript = transcript
        self.state = "RESPONDING"

    async def _end_conversation(self) -> None:
        await self._play(conversation_end_chime_pcm16(self._robot.output_sample_rate_hz))
        self.state = "IDLE"

    async def _run_sleep(self) -> None:
        # Sleep must proceed even if the spoken confirmation fails — the
        # whole point is releasing the machine (ADR 0002).
        try:
            await self._speak(SLEEP_CONFIRMATION)
            await self._wait_for_playback_tail()
        except Exception:
            logger.exception("sleep confirmation failed; sleeping anyway")
        logger.info("sleep requested by voice command")
        self._sleep_requested = True
        self.state = "IDLE"
        if self._on_sleep is not None:
            self._on_sleep()

    # Throttled diagnostic logging added live on dgx1 to answer a question
    # `hugo dev wake` couldn't: whether IDLE even sees frames, and what
    # scores look like, while vLLM/STT/TTS compete for the same CPU/GPU.
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
                return

    async def _run_listening(self, broadcaster: FrameBroadcaster) -> str | None:
        """Returns the final transcript, or None if the user never spoke
        within the window (initial wake: no_speech_timeout_s; follow-up
        window after a reply: follow_up_window_s — CONTEXT.md)."""
        self._vad.reset()
        window_s = (
            self._follow_up_window_s if self._listening_is_follow_up else self._no_speech_timeout_s
        )
        mic = broadcaster.subscribe()
        # Mic audio is buffered locally until VAD confirms speech, then the
        # buffered onset is flushed to STT. This keeps the STT server's
        # utterance state clean when the window times out with no speech —
        # nothing was ever sent, so nothing needs resetting.
        pre_roll: deque[bytes] = deque(maxlen=self._PRE_ROLL_MAX_FRAMES)
        speech_started = asyncio.Event()
        final_text: str | None = None

        async def collect_transcripts() -> None:
            nonlocal final_text
            async for t in self._stt.transcripts():
                if t.kind == "final":
                    final_text = t.text

        async def feed_audio_until_speech_ends() -> None:
            async for frame in mic:
                if not speech_started.is_set():
                    pre_roll.append(frame)
                    if self._vad.feed(frame) == "speech_start":
                        speech_started.set()
                        for buffered in pre_roll:
                            await self._stt.send_audio(buffered)
                        pre_roll.clear()
                    continue
                await self._stt.send_audio(frame)
                if self._vad.feed(frame) == "speech_end":
                    return

        turn = Turn()
        transcript_task = turn.spawn(collect_transcripts())
        feed_task = turn.spawn(feed_audio_until_speech_ends())
        try:
            try:
                async with asyncio.timeout(window_s):
                    await speech_started.wait()
            except TimeoutError:
                logger.info(
                    "no speech within %.1fs (%s window)",
                    window_s,
                    "follow-up" if self._listening_is_follow_up else "initial",
                )
                return None

            # Speech is running: wait for VAD end-of-utterance, capped so
            # ambient noise can't trap the loop in LISTENING forever.
            with contextlib.suppress(TimeoutError):
                async with asyncio.timeout(self._max_utterance_s):
                    await feed_task
            if not feed_task.done():
                logger.info("utterance hit the %.0fs cap, forcing end", self._max_utterance_s)
                feed_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await feed_task
            await self._stt.end_utterance()
            self._end_of_speech_at = asyncio.get_running_loop().time()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(transcript_task, timeout=5.0)
            self._transcript_at = asyncio.get_running_loop().time()
        finally:
            await turn.cancel_all()
        return final_text

    async def _run_responding(self, text: str, broadcaster: FrameBroadcaster) -> bool:
        """Speaks the thinker's utterances as they arrive. Returns True if
        the wake word interrupted playback (ADR 0003 as amended: wake-word
        interrupt until AEC exists)."""
        self._wake_word.reset()
        mic = broadcaster.subscribe()
        turn = Turn()
        utterances: asyncio.Queue[str | None] = asyncio.Queue()
        interrupted_event = asyncio.Event()
        now = asyncio.get_running_loop().time()
        self._first_audio_at = None
        self._last_audio_pushed_at = now

        async def produce() -> None:
            # The Thinker protocol boundary: a foreign thinker raising must
            # degrade to a spoken apology, not kill the response (the
            # original silent-death incident — see module docstring).
            try:
                async for utterance in self._thinker.think(text):
                    utterances.put_nowait(utterance)
            except Exception:
                logger.exception("thinker failed to produce a response")
                utterances.put_nowait(THINKER_FAILURE_APOLOGY)
            finally:
                utterances.put_nowait(None)

        async def speak_all() -> None:
            while True:
                utterance = await utterances.get()
                if utterance is None:
                    return
                await self._speak(utterance)

        async def watch_for_wake_interrupt() -> None:
            async for frame in mic:
                if self._wake_word.feed(frame):
                    interrupted_event.set()
                    return

        producer_task = turn.spawn(produce())
        speaker_task = turn.spawn(speak_all())
        watch_task = turn.spawn(watch_for_wake_interrupt())

        async def nudge_when_quiet() -> None:
            # Progress watchdog (VEN-56: acknowledge + updates): if nothing
            # has reached the speaker for a while and the thinker is still
            # working, say so — working and crashed must never sound the
            # same. Gap-based, so it covers slow tool calls and a slow LLM
            # pass alike.
            while not producer_task.done():
                await asyncio.sleep(self._progress_update_after_s / 2)
                quiet_for = asyncio.get_running_loop().time() - self._last_audio_pushed_at
                if quiet_for >= self._progress_update_after_s and not producer_task.done():
                    utterances.put_nowait(PROGRESS_NUDGE)
                    # Pushing the nudge resets the gap via _play once spoken;
                    # bump the marker now so a slow TTS start can't double-fire.
                    self._last_audio_pushed_at = asyncio.get_running_loop().time()

        turn.spawn(nudge_when_quiet())

        done, _pending = await asyncio.wait(
            {speaker_task, watch_task}, return_when=asyncio.FIRST_COMPLETED
        )

        interrupted = watch_task in done and interrupted_event.is_set()
        if interrupted:
            await self._tts.cancel()
            # Cancelling TTS stops *generating* audio, but chunks already
            # pushed sit in the speaker queue and would keep playing over
            # the user — flush them. clear_playback (not stop_playing,
            # which kills the shared capture pipeline — see run()).
            await self._robot.clear_playback()
            self._playback_deadline = 0.0
        await turn.cancel_all()
        if not interrupted:
            await self._wait_for_playback_tail()
        return interrupted

    async def _speak(self, text: str) -> None:
        resampler = StreamingPcm16Resampler(
            self._tts_sample_rate_hz, self._robot.output_sample_rate_hz
        )
        async for chunk in self._tts.speak(text):
            resampled = resampler.process(chunk)
            if resampled:
                await self._play(resampled)

    async def _play(self, pcm16_chunk: bytes) -> None:
        await self._robot.play_audio(pcm16_chunk)
        now = asyncio.get_running_loop().time()
        duration_s = len(pcm16_chunk) / (2 * self._robot.output_sample_rate_hz)
        self._playback_deadline = max(self._playback_deadline, now) + duration_s
        self._last_audio_pushed_at = now
        if self.state == "RESPONDING" and self._first_audio_at is None:
            self._first_audio_at = now
            if self._end_of_speech_at is not None:
                transcript_s = (self._transcript_at or now) - self._end_of_speech_at
                logger.info(
                    "turn timing: transcript %.2fs, first audio %.2fs after end of speech",
                    transcript_s,
                    now - self._end_of_speech_at,
                )

    async def _wait_for_playback_tail(self) -> None:
        # play_audio only queues; wait out the estimated real playback so
        # the follow-up window doesn't open onto HUGO's own voice (no AEC).
        remaining = self._playback_deadline - asyncio.get_running_loop().time()
        if remaining > 0:
            await asyncio.sleep(remaining)
