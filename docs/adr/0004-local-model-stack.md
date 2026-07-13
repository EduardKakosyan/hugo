# Local model stack for the DGX Spark

**Status:** accepted

HUGO's prior local attempt used MLX (Apple Silicon only), which doesn't apply on the DGX Spark's CUDA/Grace Blackwell hardware. For this iteration: Nemotron-3-super-120b-a12b (MoE, NVIDIA-tuned for agentic tool-calling) served via vLLM as the reasoning LLM; Parakeet TDT (NeMo) for STT; Qwen3-TTS for TTS; InternVL3-8B for vision. Separate specialized models per modality rather than one multimodal model, since the GB10's memory bandwidth favors sparse/small models over one large dense model doing everything, and each piece stays independently swappable. vLLM was chosen over Ollama despite requiring more manual work to satisfy the hard start/stop lifecycle (see [ADR 0002](./0002-hard-start-stop-model-lifecycle.md)), trading operational simplicity for throughput.
