# Reachy Mini Research Document

## Overview

Reachy Mini is an open-source desktop humanoid robot by Pollen Robotics. It's a compact (28cm tall, 1.5kg) expressive robot with 6-DOF head, 360-degree body rotation, 2 moveable antennas, camera, microphones, and speaker.

**SDK Repository**: https://github.com/pollen-robotics/reachy_mini
**SDK Version**: 1.2.13 (January 2026)
**License**: Apache 2.0 (software), CC BY-SA-NC (hardware)
**Python**: 3.8+ (3.10-3.13 recommended, 3.12 optimal)

## Lite vs Wireless

| Feature     | Lite ($299)                   | Wireless ($449)               |
| ----------- | ----------------------------- | ----------------------------- |
| Processing  | External computer (Mac/Linux) | Built-in Raspberry Pi 5       |
| Connection  | USB-C wired only              | Wi-Fi 6, Bluetooth 5.2        |
| Power       | Wall power (wired)            | Rechargeable battery          |
| Microphones | 2                             | 4 (array processing)          |
| IMU         | No                            | Yes (accel, gyro, quaternion) |

**Important**: Wireless does NOT support USB-C data - use Wi-Fi or USB-C-to-Ethernet adapter.

## Architecture

```
User Python Code (SDK Client)
        | (REST/WebSocket on port 8000)
    Daemon (FastAPI Server)
        | (USB/Serial or Network)
  Hardware / MuJoCo Simulator
```

- **Daemon**: FastAPI on port 8000, handles hardware I/O, safety, sensors
- **SDK**: Python client connecting over network to daemon
- **Protocols**: REST (sync), WebSocket (~10Hz bidirectional), MJPEG (camera)

## SDK API Reference

### Initialization

```python
from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

with ReachyMini(
    connection_mode="auto",      # "auto" | "localhost_only" | "network"
    media_backend="default",     # "default" | "gstreamer" | "webrtc" | "no_media"
    timeout=5.0
) as mini:
    ...
```

### Lifecycle

```python
mini.wake_up()       # Wake animation
mini.goto_sleep()    # Sleep animation
```

### Movement

```python
# Smooth interpolation
mini.goto_target(
    head=create_head_pose(z=10, roll=15, degrees=True, mm=True),
    antennas=np.array([left_rad, right_rad]),
    body_yaw=radians,
    duration=1.0,
    method="minjerk"    # "linear", "minjerk", "ease", "cartoon"
)

# Instant positioning (high-frequency control)
mini.set_target(head=pose, antennas=arr, body_yaw=val)

# Gaze control
mini.look_at_image(u, v, duration=1.0)     # Pixel coordinates
mini.look_at_world(x, y, z, duration=1.0)  # 3D world coordinates
```

### Safety Limits (Auto-clamped)

| Joint           | Range                                      |
| --------------- | ------------------------------------------ |
| Head Pitch/Roll | [-40, +40] degrees                         |
| Head Yaw        | [-180, +180] degrees                       |
| Body Yaw        | [-160, +160] degrees                       |
| Yaw Delta       | Max 65 degrees between head and body       |
| Antennas        | ~[-34, +34] degrees (~[-0.6, 0.6] radians) |

### State

```python
mini.get_current_head_pose()            # 4x4 numpy matrix
mini.get_current_joint_positions()      # (head_joints, antenna_joints)
```

### Motor Control

```python
mini.enable_motors()                              # All motors stiff
mini.enable_motors(motor_names=["body_rotation"]) # Specific motors
mini.disable_motors()                             # All motors limp
mini.enable_gravity_compensation()                # Soft mode (Placo backend only)
```

Motor IDs: body_rotation, stewart_1-6, right_antenna, left_antenna

### Camera

```python
frame = mini.media.get_frame()  # numpy (H, W, 3) uint8
```

**Note**: Lite camera may be dark by default - adjust exposure via camera control apps.

### Audio

```python
# Recording
mini.media.start_recording()
sample = mini.media.get_audio_sample()  # (samples, 2) float32 @ 16kHz
mini.media.stop_recording()

# Playback
mini.media.start_playing()
mini.media.push_audio_sample(data)      # (samples, 1-2) float32 @ 16kHz
mini.media.stop_playing()

# Direction of Arrival (4-mic wireless only)
doa = mini.media.get_DoA()

# Sample rates
input_rate = mini.media.get_input_audio_samplerate()
output_rate = mini.media.get_output_audio_samplerate()
```

### Pre-recorded Movements

Available dances: simple_nod, head_tilt_roll, side_to_side_sway, dizzy_spin, stumble_and_recover, interwoven_spirals, sharp_side_tilt, side_peekaboo, yeah_nod, uh_huh_tilt, neck_recoil, chin_lead, groovy_sway_and_roll, chicken_peck, side_glance_flick, polyrhythm_combo, grid_snap, pendulum_swing, jackson_square

```python
from reachy_mini.recorded_moves import RecordedMoves
recorded_moves = RecordedMoves()
mini.play_move(recorded_moves.get("dance_1"))
```

### App Framework

```python
from reachy_mini import ReachyMiniApp

class MyApp(ReachyMiniApp):
    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event):
        pass
```

## Daemon REST API

**Base**: `http://localhost:8000`
**Docs**: `http://localhost:8000/docs` (OpenAPI/Swagger)

| Endpoint                   | Method | Purpose                                 |
| -------------------------- | ------ | --------------------------------------- |
| `/api/daemon/status`       | GET    | Health, version, motor controller stats |
| `/api/state/full`          | GET    | Complete robot state snapshot           |
| `/api/move/set_target`     | POST   | Movement command                        |
| `/api/move/play/{dataset}` | POST   | Play pre-recorded motion                |
| `/api/camera/stream`       | GET    | MJPEG video stream                      |
| `/api/apps/install`        | POST   | Install app from HF Spaces              |
| `/api/apps/start`          | POST   | Start app                               |
| `/api/apps/stop`           | POST   | Stop app                                |
| `/api/state/ws/full`       | WS     | Real-time state streaming ~10Hz         |

## Simulator (MuJoCo)

### Installation

```bash
pip install "reachy-mini[mujoco]"
```

### Running

```bash
# Linux
reachy-mini-daemon --sim

# macOS (Apple Silicon / Intel) - requires mjpython
mjpython -m reachy_mini.daemon.app.main --sim

# With scene
reachy-mini-daemon --sim --scene minimal    # Adds table + objects

# Headless
reachy-mini-daemon --sim --headless --deactivate-audio
```

**Dashboard**: http://localhost:8000 (3D viewer, app management)

### Key Points

- Behaves exactly like Reachy Mini Lite connected via USB
- Same SDK code works for both simulator and physical robot
- Use `media_backend="no_media"` in sim mode to avoid buffer warnings
- macOS: `uv` may have MuJoCo compatibility issues, use `pip` instead

## Conversation App Reference

**Repository**: https://github.com/pollen-robotics/reachy_mini_conversation_app

Architecture:

- OpenAI Realtime API + `fastrtc` for low-latency audio
- Layered motion: primary moves + speech-reactive wobble + face-tracking
- Profile system with custom personalities
- LLM tools: move_head, dance, play_emotion, head_tracking
- Vision: Cloud (GPT realtime) or Local (SmolVLM2)
- Run: `reachy-mini-conversation-app` or `--gradio` for web UI

## Sources

- https://github.com/pollen-robotics/reachy_mini
- https://huggingface.co/docs/reachy_mini/platforms/reachy_mini_lite/get_started
- https://huggingface.co/docs/reachy_mini/platforms/simulation/get_started
- https://huggingface.co/docs/reachy_mini/v1.2.13/en/SDK/core-concept
- https://github.com/pollen-robotics/reachy_mini_conversation_app
- https://reachymini.net/
