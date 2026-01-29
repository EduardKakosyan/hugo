"""Tool/function definitions for the LLM agent."""

from __future__ import annotations

from typing import Any

# Built-in tools that the agent always has access to
BUILTIN_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "move_head",
            "description": "Move the robot's head to a target position",
            "parameters": {
                "type": "object",
                "properties": {
                    "roll": {
                        "type": "number",
                        "description": "Roll angle in degrees (-30 to 30)",
                    },
                    "pitch": {
                        "type": "number",
                        "description": "Pitch angle in degrees (-30 to 30)",
                    },
                    "yaw": {
                        "type": "number",
                        "description": "Yaw angle in degrees (-60 to 60)",
                    },
                    "duration": {
                        "type": "number",
                        "description": "Movement duration in seconds",
                        "default": 1.0,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "look_at_camera",
            "description": "Reset the robot head to look straight at the camera (neutral position)",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wave",
            "description": "Make the robot perform a friendly wave gesture",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_scene",
            "description": "Take a photo and analyze what the robot sees",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Specific question about the scene",
                        "default": "Describe what you see.",
                    }
                },
            },
        },
    },
]
