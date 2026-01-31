# Voice & Vision Research Document

## PersonaPlex 7B v1 - Analysis

### What It Is

NVIDIA's full-duplex speech-to-speech model (7B params, January 2026). Takes audio IN, produces audio OUT directly - no ASR/TTS pipeline. Based on Moshi (Kyutai).

**Performance**: 170ms turn-taking latency, 240ms interruption latency, 95% interruption success rate.

### Why It WON'T Work for HUGO

**PersonaPlex requires NVIDIA GPUs with CUDA.** No Apple Silicon support, no MLX implementation. The `brew install opus` requirement is for the Opus audio codec library (needed regardless), but the model itself needs CUDA.

- Tested on: NVIDIA A100 80GB
- Supported: Ampere (A100), Hopper (H100)
- OS: Linux preferred
- **No macOS / Apple Silicon path exists**

### Recommended Alternatives for Mac M4 Pro 48GB

## Option 1: Pipecat + MLX-Audio (RECOMMENDED)

**Source**: https://github.com/kwindla/macos-local-voice-agents

Purpose-built for real-time voice agents on macOS Apple Silicon.

**Architecture**:

- Silero VAD (Voice Activity Detection)
- MLX Whisper (Speech-to-Text)
- Kokoro-82M TTS via MLX-Audio (Text-to-Speech)
- WebRTC for low-latency audio transport

**Performance**: Voice-to-voice latency < 800ms on M-series Macs.

**Installation**:

```bash
cd server/
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Pre-download TTS model
mlx-audio.generate --model "mlx-community/Kokoro-82M-bf16" --text "Hello" --output "test.wav"
# Run
HF_HUB_OFFLINE=1 uv run bot.py
```

## Option 2: Moshi MLX (Closest to PersonaPlex)

**Source**: https://github.com/kyutai-labs/moshi

Full-duplex speech-to-speech with native MLX support for Apple Silicon.

```bash
pip install moshi_mlx
python -m moshi_mlx.local -q 4   # 4-bit quantized
python -m moshi_mlx.local_web    # Web UI at localhost:8998
```

Tested on MacBook Pro M3. Should work on M4 Pro 48GB.

## Option 3: MLX-Audio Components (Modular)

**Source**: https://github.com/Blaizzy/mlx-audio

### TTS Options

| Model      | Latency   | Parameters      | Notes                            |
| ---------- | --------- | --------------- | -------------------------------- |
| Kokoro-82M | <300ms    | 82M             | 54 voices, multilingual          |
| Qwen3-TTS  | 97ms      | 0.6-1.7B        | Voice cloning, ultra-low latency |
| Marvis TTS | Real-time | 414MB quantized | 2GB RAM, streaming               |

### STT Options

| Model               | Speed                | Notes                                 |
| ------------------- | -------------------- | ------------------------------------- |
| MLX Whisper         | Good                 | 99+ languages, well-tested            |
| Moshi STT           | Faster               | Metal API, lower latency than Whisper |
| whisper.cpp         | Good                 | Apple Neural Engine, <2GB memory      |
| NVIDIA Parakeet TDT | Extreme (RTFx >2000) | NVIDIA only                           |

### MLX-Audio API Server (OpenAI-compatible)

```bash
pip install mlx-audio
mlx_audio.server --host 0.0.0.0 --port 8000

# TTS
curl -X POST http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"mlx-community/Kokoro-82M-bf16","input":"Hello!","voice":"af_heart"}'

# STT
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=mlx-community/whisper-large-v3-turbo-asr-fp16"
```

### Python Usage

```python
# TTS
from mlx_audio.tts.utils import load_model
model = load_model("mlx-community/Kokoro-82M-bf16")
for result in model.generate("Hello!", voice="af_heart"):
    audio = result.audio

# STT
from mlx_audio.stt.generate import generate_transcription
result = generate_transcription(
    model="mlx-community/whisper-large-v3-turbo-asr-fp16",
    audio="audio.wav"
)

# Real-time streaming STT
from mlx_audio.stt.utils import load
model = load("mlx-community/VibeVoice-ASR-bf16")
for text in model.stream_transcribe(audio="speech.wav"):
    print(text, end="", flush=True)
```

## Mac M4 Pro 48GB Suitability

- 7B models: ~10-15 tok/s quantized
- 48GB unified RAM: more than sufficient for all voice models
- MLX framework optimized for Apple Silicon
- Voice-to-voice < 800ms achievable
- All models can run simultaneously (STT + LLM + TTS)

---

## Gemini Live API - Vision Processing

### What It Is

Google's real-time bidirectional WebSocket API for multimodal (vision + audio + text) interactions. Processes continuous streams with immediate responses.

### Key Specifications

- **Protocol**: WebSocket (stateful, bidirectional)
- **Video frame rate**: 1 FPS (hard limit, unsuitable for fast action)
- **Frame format**: JPEG, base64-encoded, recommended 768x768
- **Latency**: 200ms-2s typical (can spike under load)
- **SDK**: `pip install google-genai` (Python >= 3.10)

### Pricing (2026)

**Hybrid model (session + token)**:

- Session setup: $0.005
- Active time: $0.025/minute
- Video tokens: 258 tokens/second (input)
- Input tokens: $0.50/1M tokens (Gemini 2.5 Flash)
- Output tokens: $2.00/1M tokens
- **Example**: 10-min vision session ~ $0.34

**Free tier**: Available with limited RPM/TPM for development.

### Python SDK Usage

```python
from google import genai
import cv2, base64

client = genai.Client(api_key='GEMINI_API_KEY')

async with client.aio.live.connect(
    model='gemini-2.5-flash-preview',
    config={"response_modalities": ["TEXT"]}
) as session:

    # Send camera frame
    ret, frame = cv2.VideoCapture(0).read()
    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    b64 = base64.b64encode(jpeg.tobytes()).decode()

    await session.send_realtime_input(
        video={"mime_type": "image/jpeg", "data": b64}
    )

    # Receive analysis
    async for response in session.receive():
        if response.server_content:
            print(response.server_content.model_turn.parts)
```

### Key Methods

- `send_realtime_input(video=..., text=..., audio=...)` - Send multimodal data
- `send_client_content(...)` - Turn-based content
- `send_tool_response(...)` - Function call responses
- `receive()` - Async iterator for responses

### For HUGO Robot Vision

- 1 FPS is sufficient for tabletop robot monitoring
- Context retention across frames (temporal understanding)
- Natural language queries about visual scene
- Combine with voice: "What do you see?" queries
- Session management: reconnect every 10-15 min to avoid context bloat
- Use Free Tier for dev, Tier 1 for production

### Limitations

- 1 FPS hard limit (no fast motion analysis)
- Only JPEG frames (no native video codec streaming)
- Latency varies (200ms-15s under load)
- Context window tokens accumulate (cost grows over session)
- No published SLAs for latency/uptime

## Sources

- https://huggingface.co/nvidia/personaplex-7b-v1
- https://github.com/NVIDIA/personaplex
- https://github.com/kyutai-labs/moshi
- https://github.com/Blaizzy/mlx-audio
- https://github.com/kwindla/macos-local-voice-agents
- https://ai.google.dev/gemini-api/docs/live
- https://docs.cloud.google.com/vertex-ai/generative-ai/docs/live-api
- https://github.com/googleapis/python-genai
- https://github.com/SAGE-Rebirth/gemini-live
