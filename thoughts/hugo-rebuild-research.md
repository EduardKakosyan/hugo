# HUGO Rebuild Research

## Reachy Mini Robot — Hardware Specifications

- **Height**: 28cm (23cm in sleep mode)
- **Width**: 16cm
- **Weight**: 1.5 kg
- **Movement**: 6 DoF head, 360-degree body rotation, 2 independently animated antennas
- **Camera**: Wide-angle
- **Audio**: 4 microphones, 5W speaker
- **IMU**: Accelerometer, gyroscope, quaternion, temperature (Wireless version only)
- **Variants**: Lite ($299, USB-connected) and Wireless ($449, RPi 4, battery, autonomous)
- **License**: Apache 2.0 (software), CC BY-SA-NC (hardware)

## Reachy Mini SDK — Python API Reference

### Main Class: `ReachyMini`

```python
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

# Constructor
mini = ReachyMini(
    connection_mode="auto",  # "auto" | "localhost_only" | "network"
    media_backend="default", # "default" | "gstreamer" | "webrtc" | "no_media"
    timeout=5.0,
)

# Supports context manager
with ReachyMini() as mini:
    ...
```

### Lifecycle

```python
mini.wake_up()      # Wake animation
mini.goto_sleep()   # Sleep animation
```

### Movement

```python
# Smooth interpolation (methods: "linear", "minjerk", "ease", "cartoon")
mini.goto_target(
    head=create_head_pose(z=10, roll=15, degrees=True, mm=True),
    antennas=np.array([left_rad, right_rad]),
    body_yaw=radians,
    duration=1.0,
    method="minjerk",
)

# Immediate positioning (no interpolation, for high-frequency control)
mini.set_target(head=pose, antennas=arr, body_yaw=val)

# Gaze control
mini.look_at_image(u, v, duration=1.0)      # Pixel coordinates
mini.look_at_world(x, y, z, duration=1.0)   # 3D world coordinates
```

### Utility Functions

```python
# Create 4x4 head pose matrix from human-readable params
create_head_pose(x=0, y=0, z=0, roll=0, pitch=0, yaw=0, mm=False, degrees=True)
```

### State

```python
mini.get_current_head_pose()           # Returns 4x4 numpy matrix
mini.get_current_joint_positions()     # Returns (head_joints, antenna_joints)
```

### Camera

```python
mini.media.get_frame()  # Returns numpy array (H, W, 3) uint8
```

### Audio

```python
mini.media.start_recording()
mini.media.stop_recording()
mini.media.start_playing()
mini.media.stop_playing()
mini.media.get_audio_sample()       # Returns (samples, 2) float32 @ 16kHz
mini.media.push_audio_sample(data)  # Accepts (samples, 1-2) float32 @ 16kHz
mini.media.get_DoA()                # Direction of arrival + speech detection
mini.media.get_input_audio_samplerate()
mini.media.get_output_audio_samplerate()
mini.media.get_input_channels()
mini.media.get_output_channels()
```

### IMU (Wireless only)

```python
mini.imu  # Dict with: accelerometer (m/s²), gyroscope (rad/s), quaternion (w,x,y,z), temperature (°C)
```

### Motion Recording

```python
mini.start_recording()   # Capture motion sequences
mini.stop_recording()    # Returns recorded data
```

### Kinematics

- `AnalyticalKinematics` — Rust-based, fastest analytical approach
- `PlacoKinematics` — URDF-based with collision detection
- `NNKinematics` — Neural network from Placo training data

### App Framework

```python
from reachy_mini import ReachyMiniApp

class MyApp(ReachyMiniApp):
    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        # App logic here
        pass
```

## Daemon

- **Simulator**: `reachy-mini-daemon --sim` (MuJoCo-based)
- **Headless**: `reachy-mini-daemon --sim --headless --deactivate-audio`
- **Custom scene**: `mjpython -m reachy_mini.daemon.app.main --sim --scene minimal`
- **Port**: FastAPI on port 8000 + WebSocket for video/audio
- **Protocol**: SDK connects to daemon via gRPC
- **Architecture**: `User Code -> SDK (Python) -> gRPC -> Daemon -> Robot/Simulator`

## Pollen's Official Conversation App

**Repository**: `pollen-robotics/reachy_mini_conversation_app`

### Architecture

- Real-time audio conversation loop via **OpenAI Realtime API** + `fastrtc`
- Layered motion system: primary moves (dances, emotions, goto, breathing) + speech-reactive wobble + face-tracking
- Profile system with custom personalities (`instructions.txt` + `tools.txt`)

### LLM Tools

| Tool            | Function                       |
| --------------- | ------------------------------ |
| `move_head`     | Queue head pose changes        |
| `dance`         | Queue dances from library      |
| `play_emotion`  | Execute recorded emotion clips |
| `head_tracking` | Enable/disable face-tracking   |

### Vision Modes

- Cloud: gpt-realtime processes camera frames
- Local: SmolVLM2 model on-device (CPU/GPU/MPS)

### Deployment

- `reachy-mini-conversation-app` (console)
- `--gradio` flag for web UI
- Install via `uv sync`

## Pollen's Desktop App

**Repository**: `pollen-robotics/reachy-mini-desktop-app`

### Tech Stack

- **Frontend**: React + Material-UI + Zustand
- **Backend**: Tauri 2.0 (Rust) + Python sidecar (FastAPI)
- **Communication**: REST + WebSocket (20Hz state updates)

### Features

- Real-time 3D visualization with X-ray effects
- USB auto-detection, WiFi/mDNS discovery
- App store (Hugging Face Spaces)
- Joystick/slider controls, emotion wheel
- Live camera feed, audio controls
- macOS permissions, auto-updates

## PyPI Package

- **Name**: `reachy-mini`
- **Current Version**: 1.2.13 (Jan 21, 2026)
- **Python**: >=3.10
- **Optional extras**: `dev`, `examples`, `mujoco`, `nn-kinematics`, `placo-kinematics`, `gstreamer`, `rerun`, `wireless-version`

## Current HUGO Codebase (Pre-Rebuild)

### Backend Structure

```
backend/src/
  main.py           — FastAPI entry (lifespan: sim daemon, robot, integrations, agent)
  config.py         — Pydantic settings from env + YAML
  robot/
    controller.py   — ReachyMini wrapper (custom _rpy_to_pose matrix math)
    simulator.py    — Subprocess manager for reachy-mini-daemon --sim
  agent/
    core.py         — AgentOrchestrator (single-round tool calls, streaming)
    providers.py    — LiteLLM multi-provider (Gemini, OpenAI, Anthropic, Ollama)
    tools.py        — 4 tools: move_head, look_at_camera, wave, analyze_scene
  voice/
    engine.py       — Manager switching PersonaPlex vs cloud fallback
    fallback.py     — Cloud STT/TTS stub
    personaplex.py  — PersonaPlex engine stub
  vision/
    camera.py       — Frame capture + JPEG streaming
    processor.py    — Multimodal LLM vision analysis
  integrations/
    base.py         — Integration ABC
    registry.py     — Plugin lifecycle (discover, load, configure, teardown)
    calendar.py     — Google Calendar (stub)
    outlook.py      — Outlook (stub)
    obsidian.py     — Obsidian (stub)
  api/
    routes.py       — REST: status, chat, move, integrations, settings
    schemas.py      — Pydantic request/response models
    websocket.py    — WS: telemetry, video relay, audio, chat, logs
```

### Frontend Structure

```
frontend/src/
  routes/+page.svelte       — Dashboard: 3D viewer + tabs (controls, chat, logs)
  routes/+layout.svelte     — Root layout
  lib/components/
    RobotViewer3D.svelte     — Three.js + URDF robot visualization
    RobotController.svelte   — Sliders for head/antenna/body
    ChatPanel.svelte         — Chat tab
    AudioControls.svelte     — Audio status bar
    LogsPanel.svelte         — Backend log viewer
    PowerControls.svelte     — Wake/sleep buttons
  lib/stores/
    robotStore.ts            — Telemetry WebSocket
    chatStore.ts             — Chat WebSocket
    settingsStore.ts         — App settings
    logsStore.ts             — Logs WebSocket
  lib/types/index.ts         — TypeScript interfaces
```

### Key Dependencies

- **Backend**: FastAPI, Pydantic, LiteLLM, reachy-mini[mujoco], numpy, Pillow, httpx
- **Frontend**: SvelteKit 5, Tailwind v4, Three.js, urdf-loader

### What Works

- Robot connection via ReachyMini SDK (gRPC)
- Head/antenna/body movement via sliders
- LLM chat with basic tool calling (single round)
- Camera streaming via WebSocket relay
- Telemetry at configurable Hz
- Integration plugin system (all stubs)

### What Needs Rebuilding

- Single-round tool calling → multi-turn loop
- Manual controls → AI-driven movement
- 3D viewer → live camera feed
- Stub voice → real STT/TTS pipeline
- Custom simulator management → external daemon
- Dashboard-first UI → chat-first UI
- Custom matrix math → SDK utilities (create_head_pose)
