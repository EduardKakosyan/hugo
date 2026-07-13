# Python as the primary implementation language

**Status:** accepted

HUGO has been rewritten three times, alternating between Go (learning-motivated, cloud Claude API, tRPC-agent-go) and Python (CrewAI + Pipecat + MLX, fully local). Reachy Mini's SDK is Python-only with no Go bindings, and both prior "fully local" attempts converged on Python's local-inference ecosystem (MLX, whisper.cpp-style tooling). We're committing to Python as the primary language for this iteration so robot control and model inference don't require a cross-language bridge. Go's concurrency model was attractive for the listen/speak/interrupt pipeline, but asyncio/threading covers that need without splitting the stack.
