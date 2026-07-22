"""Shared fakes for voice loop tests — no hardware, no real model inference.
Deliberately simple/scriptable so barge-in timing can be controlled
precisely from the test rather than relying on real-time sleeps."""

import asyncio
from collections.abc import AsyncIterator

from hugo.voice.stt import Transcript
from hugo.voice.vad import SpeechEvent

WAKE_MARKER = b"WAKE"
SPEECH_START_MARKER = b"SPEECH_START"
SPEECH_END_MARKER = b"SPEECH_END"


class FakeRobotAudioIO:
    input_sample_rate_hz = 16_000
    output_sample_rate_hz = 24_000

    def __init__(self) -> None:
        self._frame_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.recording = False
        self.playing = False
        self.played_chunks: list[bytes] = []
        self.closed = False

    def push_frame(self, frame: bytes) -> None:
        self._frame_queue.put_nowait(frame)

    async def start_recording(self) -> None:
        self.recording = True

    async def stop_recording(self) -> None:
        self.recording = False

    async def read_mic_frames(self) -> AsyncIterator[bytes]:
        while True:
            frame = await self._frame_queue.get()
            if frame is None:
                return
            yield frame

    async def start_playing(self) -> None:
        self.playing = True

    async def stop_playing(self) -> None:
        self.playing = False

    async def play_audio(self, pcm16_chunk: bytes) -> None:
        self.played_chunks.append(pcm16_chunk)

    def close(self) -> None:
        self.closed = True


class FakeWakeWordListener:
    def __init__(self) -> None:
        self.reset_count = 0
        self.last_score = 0.0

    def feed(self, pcm16_chunk: bytes) -> bool:
        self.last_score = 1.0 if pcm16_chunk == WAKE_MARKER else 0.0
        return pcm16_chunk == WAKE_MARKER

    def reset(self) -> None:
        self.reset_count += 1


class FakeSpeechDetector:
    def __init__(self) -> None:
        self.reset_count = 0

    def feed(self, pcm16_chunk: bytes) -> SpeechEvent | None:
        if pcm16_chunk == SPEECH_START_MARKER:
            return "speech_start"
        if pcm16_chunk == SPEECH_END_MARKER:
            return "speech_end"
        return None

    def reset(self) -> None:
        self.reset_count += 1


class FakeSttSession:
    def __init__(self, final_text: str = "hello hugo") -> None:
        self.sent_audio: list[bytes] = []
        self.ended = False
        self.final_text = final_text
        self._end_event = asyncio.Event()

    async def send_audio(self, pcm16_chunk: bytes) -> None:
        self.sent_audio.append(pcm16_chunk)

    async def end_utterance(self) -> None:
        self.ended = True
        self._end_event.set()

    async def transcripts(self) -> AsyncIterator[Transcript]:
        await self._end_event.wait()
        yield Transcript(kind="final", text=self.final_text)


class FakeTtsSession:
    def __init__(self, chunks: list[bytes] | None = None, chunk_delay: float = 0.01) -> None:
        self._chunks = chunks if chunks is not None else [b"a", b"b", b"c", b"d", b"e"]
        self._chunk_delay = chunk_delay
        self.cancelled = False
        self.spoken_text: str | None = None

    async def speak(self, text: str) -> AsyncIterator[bytes]:
        self.spoken_text = text
        for chunk in self._chunks:
            if self.cancelled:
                return
            await asyncio.sleep(self._chunk_delay)
            yield chunk

    async def cancel(self) -> None:
        self.cancelled = True


class FakeThinker:
    def __init__(self, response: str = "hello there") -> None:
        self.response = response
        self.asked: str | None = None

    async def think(self, user_text: str) -> str:
        self.asked = user_text
        return self.response
