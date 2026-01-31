from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "HUGO_", "env_file": ".env"}

    # OpenClaw
    openclaw_url: str = "ws://127.0.0.1:18789"
    openclaw_token: str = ""

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # Voice
    stt_model: str = "mlx-community/whisper-large-v3-turbo"
    tts_model: str = "mlx-community/Kokoro-82M-bf16"
    tts_voice: str = "af_heart"
    sample_rate: int = 16000
    vad_threshold: float = 0.5

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    backend_url: str = "http://localhost:8080"

    # Vision
    vision_provider: str = "gemini"
    mlx_vision_model: str = "mlx-community/Qwen3-VL-4B-Instruct-8bit"

    # Camera
    camera_index: int = 0


settings = Settings()
