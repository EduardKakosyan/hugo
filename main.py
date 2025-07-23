#!/usr/bin/env python3
"""
Gemini Live Voice Chat - Simple & Reliable
Press Enter to record, Enter again to stop and get AI response
"""

import asyncio
import os
import sys
import time
import pyaudio
import numpy as np
import wave
import tempfile
import speech_recognition as sr
import warnings
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Comprehensive warning suppression
warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*inline_data.*")
warnings.filterwarnings("ignore", category=UserWarning)

# Also suppress logging warnings
logging.getLogger().setLevel(logging.ERROR)

# Suppress specific warnings using the warnings module
warnings.filterwarnings("ignore", message=".*non-text parts.*")
warnings.filterwarnings("ignore", message=".*inline_data.*")
warnings.filterwarnings("ignore", category=UserWarning)
os.system('cls' if os.name == 'nt' else 'clear')

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Load API key
load_dotenv(".env.local")
api_key = os.getenv("PRIVATE_GOOGLE_API_KEY")
if not api_key:
    print("❌ No API key found in .env.local")
    sys.exit(1)
os.environ["GOOGLE_API_KEY"] = api_key

class VoiceChat:
    def __init__(self):
        self.client = genai.Client(http_options={"api_version": "v1beta"})
        self.audio = pyaudio.PyAudio()
        self.recognizer = sr.Recognizer()
        self.session = None
        
        # State
        self.is_recording = False
        self.audio_frames = []
        self.start_time = 0
        
        # Playback
        self.audio_queue = asyncio.Queue()
        
        # Config
        self.config = {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {"prebuilt_voice_config": {"voice_name": "Aoede"}}
            }
        }
    
    def print_welcome(self):
        print("🎙️ " + "="*60 + " 🎙️")
        print("           GEMINI LIVE VOICE CHAT")
        print("🎙️ " + "="*60 + " 🎙️")
        print()
        print("🚀 Simple Commands:")
        print("   ENTER = Start/Stop Recording")  
        print("   'quit' = Exit")
        print()
        print("✨ Features:")
        print("   🎵 Real-time volume feedback")
        print("   📝 Speech transcription")
        print("   🤖 AI voice responses")
        print("   🔊 Streaming audio playback")
        print()
        print("="*66)
    
    def volume_bar(self, volume, max_width=30):
        """Create volume visualization"""
        normalized = min(volume / 1000, 1.0)
        filled = int(normalized * max_width)
        bar = "█" * filled + "░" * (max_width - filled)
        
        if volume < 50:
            color = "🔇"
        elif volume < 200:
            color = "🔉"
        else:
            color = "🔊"
            
        return f"{color} │{bar}│ {volume:4.0f}"
    
    async def record_voice(self):
        """Record audio with visual feedback"""
        print("\n🎤 RECORDING... Press ENTER to stop")
        
        self.audio_frames = []
        self.start_time = time.time()
        
        # Setup audio stream
        stream = self.audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK
        )
        
        self.is_recording = True
        
        # Record in background task
        async def record_loop():
            while self.is_recording:
                try:
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    self.audio_frames.append(data)
                    
                    # Volume feedback
                    audio_array = np.frombuffer(data, dtype=np.int16)
                    volume = np.abs(audio_array).mean()
                    elapsed = time.time() - self.start_time
                    
                    bar = self.volume_bar(volume)
                    print(f"\r{bar} │ {elapsed:.1f}s", end="", flush=True)
                    
                    await asyncio.sleep(0.01)
                except (OSError, Exception):
                    break
        
        # Start recording
        record_task = asyncio.create_task(record_loop())
        
        # Wait for user to stop
        await asyncio.to_thread(input)
        self.is_recording = False
        await record_task
        
        stream.stop_stream()
        stream.close()
        print()
        
        if self.audio_frames:
            audio_data = b''.join(self.audio_frames)
            duration = len(self.audio_frames) * CHUNK / RATE
            print(f"✅ Recorded {duration:.1f} seconds")
            return audio_data
        return None
    
    async def transcribe(self, audio_data):
        """Transcribe audio to text"""
        print("🔄 Transcribing...")
        
        try:
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                temp_path = f.name
            
            with wave.open(temp_path, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.audio.get_sample_size(FORMAT))
                wf.setframerate(RATE)
                wf.writeframes(audio_data)
            
            # Transcribe
            with sr.AudioFile(temp_path) as source:
                audio = self.recognizer.record(source)
            
            text = self.recognizer.recognize_google(audio)
            print(f"📝 You said: \"{text}\"")
            
            os.unlink(temp_path)
            return text
            
        except sr.UnknownValueError:
            print("❓ Couldn't understand audio")
            return None
        except Exception as e:
            print(f"❌ Transcription error: {e}")
            return None
    
    async def send_message(self, text):
        """Send to Gemini and get response"""
        print("🤖 Asking Gemini...")
        
        try:
            # Send message
            await self.session.send_client_content(
                turns=types.Content(
                    role="user",
                    parts=[types.Part(text=text)]
                ),
                turn_complete=True
            )
            
            # Get response
            await self.get_response()
            
        except Exception as e:
            print(f"❌ Error communicating with Gemini: {e}")
    
    async def get_response(self):
        """Handle Gemini's response"""
        print("🎧 Receiving response...")
        
        try:
            turn = self.session.receive()
            chunk_count = 0
            
            async with asyncio.timeout(15):
                async for response in turn:
                    if hasattr(response, 'data') and response.data:
                        chunk_count += 1
                        await self.audio_queue.put(response.data)
                        
                        if chunk_count == 1:
                            print("🔊 Playing Gemini's response...")
                            # Start playback
                            asyncio.create_task(self.play_audio())
                        
                        if chunk_count % 10 == 0:
                            print(f"📡 Streaming... ({chunk_count} chunks)")
                    
                    if hasattr(response, 'text') and response.text:
                        print(f"💭 Gemini: {response.text}")
            
            # Signal end
            await self.audio_queue.put(None)
            
            if chunk_count > 0:
                print(f"✅ Response complete ({chunk_count} audio chunks)")
            else:
                print("❌ No audio response received")
                
        except asyncio.TimeoutError:
            print("⏰ Response timeout")
        except Exception as e:
            print(f"❌ Response error: {e}")
    
    async def play_audio(self):
        """Play audio from queue"""
        try:
            # Setup playback
            stream = self.audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=GEMINI_AUDIO_RATE,  # Gemini output rate
                output=True
            )
            
            played = 0
            while True:
                try:
                    chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=2.0)
                    if chunk is None:
                        break
                    stream.write(chunk)
                    played += 1
                except asyncio.TimeoutError:
                    break
            
            stream.close()
            print(f"🔈 Playback finished ({played} chunks)")
            
        except Exception as e:
            print(f"❌ Playback error: {e}")
    
    async def chat_loop(self):
        """Main interaction loop"""
        print("\n🟢 Ready! Press ENTER to start recording...")
        
        while True:
            try:
                command = await asyncio.to_thread(
                    input, "\n🎙️  Press ENTER to record (or 'quit'): "
                )
                
                if command.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                # Record voice
                audio_data = await self.record_voice()
                if not audio_data:
                    continue
                
                # Transcribe
                text = await self.transcribe(audio_data)
                if not text:
                    continue
                
                # Send to Gemini
                await self.send_message(text)
                
                # Wait for playback to finish
                await asyncio.sleep(1)
                
            except KeyboardInterrupt:
                print("\n👋 Interrupted")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
    
    async def run(self):
        """Start the voice chat"""
        self.print_welcome()
        
        try:
            print("🔌 Connecting to Gemini...")
            async with self.client.aio.live.connect(
                model="models/gemini-2.0-flash-live-001",
                config=self.config
            ) as session:
                self.session = session
                print("✅ Connected!")
                
                await self.chat_loop()
                
        except Exception as e:
            print(f"💥 Connection failed: {e}")
        finally:
            self.audio.terminate()

def main():
    chat = VoiceChat()
    asyncio.run(chat.run())

if __name__ == "__main__":
    main()