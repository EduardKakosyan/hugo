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
from hugo.voice.stt import Transcript
from hugo.voice.turn import Turn
from hugo.voice.vad import SpeechEvent

logger = logging.getLogger(__name__)

State = Literal["IDLE", "LISTENING", "THINKING", "SPEAKING"]


class WakeWordListener(Protocol):
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
    ) -> None:
        self._robot = robot
        self._wake_word = wake_word
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._thinker = thinker
        self.state: State = "IDLE"
        self._pending_transcript: str = ""
        self._pending_response: str = ""

    async def run(self) -> None:
        await self._robot.start_recording()
        broadcaster = FrameBroadcaster(self._robot.read_mic_frames())
        broadcaster.start()
        try:
            while True:
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
        finally:
            await broadcaster.stop()
            await self._robot.stop_recording()

    async def _run_idle(self, broadcaster: FrameBroadcaster) -> None:
        self._wake_word.reset()
        async for frame in broadcaster.subscribe():
            if self._wake_word.feed(frame):
                self.state = "LISTENING"
                return

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
        return await self._thinker.think(user_text)

    async def _run_speaking(self, text: str, broadcaster: FrameBroadcaster) -> bool:
        """Returns True if barge-in interrupted playback (caller should go
        straight to LISTENING to capture what the user just said)."""
        self._vad.reset()
        mic = broadcaster.subscribe()
        turn = Turn()
        barge_in_event = asyncio.Event()

        async def play() -> None:
            await self._robot.start_playing()
            try:
                async for chunk in self._tts.speak(text):
                    await self._robot.play_audio(chunk)
            finally:
                await self._robot.stop_playing()

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
        await turn.cancel_all()
        return interrupted
