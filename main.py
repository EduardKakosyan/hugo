#!/usr/bin/env python3
"""
Gemini Live Audio Chat - Terminal Application
"""

import asyncio
import os
import pyaudio
import numpy as np
import wave
import tempfile
import speech_recognition as sr
import time
from enum import Enum
from google import genai
from dotenv import load_dotenv

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.0-flash-live-001"

# Load environment variables
load_dotenv(".env.local")
api_key = os.getenv("PRIVATE_GOOGLE_API_KEY")

if not api_key:
    print("❌ Please set PRIVATE_GOOGLE_API_KEY in .env.local file")
    exit(1)

os.environ["GOOGLE_API_KEY"] = api_key

client = genai.Client(http_options={"api_version": "v1beta"})
CONFIG = {
    "response_modalities": ["AUDIO"],
    "speech_config": {
        "voice_config": {
            "prebuilt_voice_config": {
                "voice_name": "Aoede"
            }
        }
    }
}

pya = pyaudio.PyAudio()


class ConversationState(Enum):
    WAITING = "waiting"
    RECORDING = "recording" 
    PROCESSING = "processing"
    PLAYING = "playing"

class AudioLoop:
    def __init__(self):
        self.audio_in_queue = None
        self.out_queue = None
        self.session = None
        
        # State management
        self.state = ConversationState.WAITING
        self.audio_buffer = []
        self.last_state_change = time.time()
        
        # Audio processing
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 2000
        self.transcription_enabled = True
        
        # Real-time feedback
        self.recording_start_time = None
        self.volume_history = []

    def set_state(self, new_state: ConversationState):
        """Change conversation state with logging"""
        if self.state != new_state:
            old_state = self.state.value
            self.state = new_state
            self.last_state_change = time.time()
            print(f"\n🔄 State: {old_state} → {new_state.value}")

    def get_state_indicator(self):
        """Get visual indicator for current state"""
        indicators = {
            ConversationState.WAITING: "⏸️  Press Enter to start recording",
            ConversationState.RECORDING: "🎤 Recording... Press Enter to stop",
            ConversationState.PROCESSING: "🧠 Gemini is thinking...",
            ConversationState.PLAYING: "🔊 Gemini is speaking (Press Enter to interrupt)"
        }
        return indicators.get(self.state, "❓ Unknown state")

    def show_volume_meter(self, volume_level):
        """Show real-time volume meter"""
        max_bars = 20
        bars = int((volume_level / 1000) * max_bars)
        meter = "█" * bars + "░" * (max_bars - bars)
        elapsed = time.time() - self.recording_start_time if self.recording_start_time else 0
        print(f"\r🎤 [{meter}] {volume_level:4.0f} | {elapsed:.1f}s", end="", flush=True)

    async def handle_user_input(self):
        """Main user interaction loop with state machine"""
        while True:
            try:
                if self.state == ConversationState.WAITING:
                    command = await asyncio.to_thread(input, f"\n{self.get_state_indicator()}: ")
                    
                    if command.lower() == "q":
                        break
                    elif command.strip() == "":
                        # Start recording
                        await self.start_recording()
                    else:
                        # Handle text input
                        await self.send_text_message(command)
                        
                elif self.state in [ConversationState.RECORDING, ConversationState.PLAYING]:
                    # Wait for Enter press to stop recording or interrupt
                    await asyncio.to_thread(input)
                    
                    if self.state == ConversationState.RECORDING:
                        await self.stop_recording()
                    elif self.state == ConversationState.PLAYING:
                        await self.interrupt_playback()
                        
                else:
                    # In PROCESSING state, just wait
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"\n❌ Input error: {e}")
                
        return True  # Signal to exit

    async def start_recording(self):
        """Start voice recording with visual feedback"""
        self.set_state(ConversationState.RECORDING)
        self.audio_buffer = []
        self.recording_start_time = time.time()
        self.volume_history = []

    async def stop_recording(self):
        """Stop recording and process audio"""
        self.set_state(ConversationState.PROCESSING)
        
        if self.audio_buffer:
            # Show transcription
            if self.transcription_enabled:
                await self.transcribe_buffer()
            
            # Send end of turn to trigger Gemini response
            await self.session.send(input=".", end_of_turn=True)
        else:
            print("\n❓ No audio recorded")
            self.set_state(ConversationState.WAITING)

    async def send_text_message(self, text):
        """Send text message to Gemini"""
        self.set_state(ConversationState.PROCESSING)
        await self.session.send(input=text, end_of_turn=True)

    async def interrupt_playback(self):
        """Interrupt Gemini playback and start recording"""
        print("\n⚡ Interrupting Gemini...")
        # Clear audio queue
        while not self.audio_in_queue.empty():
            self.audio_in_queue.get_nowait()
        
        # Start new recording
        await self.start_recording()

    async def send_realtime(self):
        """Send audio data from queue to session"""
        while True:
            try:
                msg = await self.out_queue.get()
                await self.session.send(input=msg)
            except Exception as e:
                print(f"❌ Send realtime error: {e}")
                await asyncio.sleep(0.1)

    async def listen_audio(self):
        """Capture audio from microphone with real-time volume feedback"""
        try:
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
                if self.state == ConversationState.RECORDING:
                    try:
                        data = await asyncio.to_thread(
                            self.audio_stream.read, CHUNK_SIZE, exception_on_overflow=False
                        )
                        
                        # Calculate volume for visual feedback
                        audio_array = np.frombuffer(data, dtype=np.int16)
                        volume = np.abs(audio_array).mean()
                        self.show_volume_meter(volume)
                        
                        # Store audio for transcription and sending
                        self.audio_buffer.append(data)
                        await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})
                        
                    except Exception as e:
                        print(f"\n❌ Audio capture error: {e}")
                else:
                    await asyncio.sleep(0.05)  # Faster polling for responsiveness
                    
        except Exception as e:
            print(f"❌ Microphone setup error: {e}")

    async def receive_audio(self):
        """Background task to read from the websocket and handle Gemini responses"""
        while True:
            try:
                turn = self.session.receive()
                first_chunk = True
                
                async for response in turn:
                    if data := response.data:
                        # Start playing state on first audio chunk
                        if first_chunk and self.state == ConversationState.PROCESSING:
                            self.set_state(ConversationState.PLAYING)
                            first_chunk = False
                            
                        # Only queue audio if we're in playing state (not interrupted)
                        if self.state == ConversationState.PLAYING:
                            self.audio_in_queue.put_nowait(data)
                        continue
                        
                    if text := response.text:
                        print(f"\n💭 Gemini: {text}")

                # Turn complete - go back to waiting
                if self.state == ConversationState.PLAYING:
                    # Wait for audio queue to empty before switching to waiting
                    await asyncio.sleep(0.5)  # Brief delay for audio to finish
                    self.set_state(ConversationState.WAITING)
                
                # Clear any remaining audio if interrupted
                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
                    
            except Exception as e:
                print(f"❌ Receive audio error: {e}")
                await asyncio.sleep(1)

    async def play_audio(self):
        """Play audio from queue with state awareness"""
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        
        while True:
            # Only play when in PLAYING state
            if self.state == ConversationState.PLAYING:
                try:
                    bytestream = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.1)
                    await asyncio.to_thread(stream.write, bytestream)
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(0.1)

    async def run(self):
        """Main run loop with state machine"""
        print("\n🎙️  Gemini Live Audio Chat - Advanced Edition")
        print("=" * 50)
        print("🎤 Interactive Voice Chat with Real-time Feedback")
        print("💫 Features:")
        print("   • Real-time volume meters during recording")
        print("   • Live transcription of your speech")
        print("   • Interrupt Gemini by pressing Enter")
        print("   • Smart state management")
        print("   • Type 'q' to quit anytime")
        print("=" * 50)

        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session
                print("✅ Connected to Gemini Live API")

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                # Create all background tasks
                user_input_task = tg.create_task(self.handle_user_input())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                # Wait for user to quit
                await user_input_task
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if hasattr(self, "audio_stream"):
                self.audio_stream.close()
            print("\n👋 Thanks for using Gemini Live Audio Chat!")
    
    async def transcribe_buffer(self):
        """Transcribe the audio buffer with enhanced feedback"""
        try:
            print("\n🔍 Transcribing your speech...")
            
            # Combine audio chunks
            audio_data = b''.join(self.audio_buffer)
            duration = len(audio_data) / (SEND_SAMPLE_RATE * 2)
            
            # Save to temporary WAV file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                tmp_filename = tmp_file.name
                
            with wave.open(tmp_filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(pya.get_sample_size(FORMAT))
                wf.setframerate(SEND_SAMPLE_RATE)
                wf.writeframes(audio_data)
            
            # Transcribe
            with sr.AudioFile(tmp_filename) as source:
                audio = self.recognizer.record(source)
                
            try:
                text = self.recognizer.recognize_google(audio)
                print(f"📝 You said ({duration:.1f}s): \"{text}\"")
                return text
            except sr.UnknownValueError:
                print("❓ Could not understand the audio (try speaking more clearly)")
                return None
            except sr.RequestError as e:
                print(f"❌ Transcription service error: {e}")
                return None
            
            # Clean up
            os.unlink(tmp_filename)
            
        except Exception as e:
            print(f"❌ Error during transcription: {e}")
            return None


def main():
    app = AudioLoop()
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
