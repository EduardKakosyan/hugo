#!/usr/bin/env python3
"""
Gemini Live Audio Chat - Terminal Application
"""

import asyncio
import os
import sys
import pyaudio
from google import genai
from dotenv import load_dotenv

# Python 3.11 compatibility
if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.0-flash-live-001"

# Load environment variables
load_dotenv('.env.local')
api_key = os.getenv("PRIVATE_GOOGLE_API_KEY")

if not api_key:
    print("❌ Please set PRIVATE_GOOGLE_API_KEY in .env.local file")
    exit(1)

os.environ["GOOGLE_API_KEY"] = api_key

client = genai.Client(http_options={"api_version": "v1beta"})
CONFIG = {"response_modalities": ["AUDIO"]}

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        self.is_recording = False

    async def send_text(self):
        """Handle text commands"""
        while True:
            text = await asyncio.to_thread(
                input,
                "\n💬 Type message or press Enter to use voice (q to quit): ",
            )
            if text.lower() == "q":
                break
            elif text == "":
                # Start voice recording
                await self.voice_interaction()
            else:
                # Send text message
                await self.session.send(input=text, end_of_turn=True)

    async def voice_interaction(self):
        """Handle voice recording and playback"""
        print("🎤 Recording... Press Enter to stop")
        
        # Start recording
        self.is_recording = True
        
        # Wait for Enter to stop
        await asyncio.to_thread(input)
        
        # Stop recording and wait for response
        self.is_recording = False
        
        # Send end of turn to get response
        await self.session.send(input=".", end_of_turn=True)
        
        print("⏸️  Recording stopped. Playing response...")
        
        # Wait a moment for the response to complete
        await asyncio.sleep(2)

    async def send_realtime(self):
        """Send audio data from queue to session"""
        while True:
            msg = await self.out_queue.get()
            await self.session.send(input=msg)

    async def listen_audio(self):
        """Capture audio from microphone"""
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        
        while True:
            if self.is_recording:
                try:
                    data = await asyncio.to_thread(
                        self.audio_stream.read, 
                        CHUNK_SIZE, 
                        exception_on_overflow=False
                    )
                    await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
                except Exception as e:
                    print(f"Audio error: {e}")
            else:
                await asyncio.sleep(0.1)

    async def receive_audio(self):
        """Receive responses from Gemini"""
        while True:
            turn = self.session.receive()
            async for response in turn:
                if data := response.data:
                    # Only play audio when not recording
                    if not self.is_recording:
                        self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(f"\n🤖 Gemini: {text}")

            # Clear audio queue on turn complete
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        """Play audio from queue"""
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        
        while True:
            if not self.is_recording:
                try:
                    bytestream = await asyncio.wait_for(
                        self.audio_in_queue.get(), 
                        timeout=0.1
                    )
                    await asyncio.to_thread(stream.write, bytestream)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(0.1)

    async def run(self):
        """Main run loop"""
        print("\n🎙️  Gemini Live Audio Chat")
        print("=" * 40)
        print("• Press Enter for voice input")
        print("• Type text for text input")
        print("• Type 'q' to quit")
        print("=" * 40)
        
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                print("✅ Connected to Gemini Live API\n")

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                # Create all tasks
                send_text_task = tg.create_task(self.send_text())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                # Wait for user to quit
                await send_text_task
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"\n❌ Error: {e}")
        finally:
            if hasattr(self, 'audio_stream'):
                self.audio_stream.close()
            print("\n👋 Goodbye!")


def main():
    app = AudioLoop()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
