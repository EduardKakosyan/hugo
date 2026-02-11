# AGENTS.md

Agent architecture for HUGO personal assistant.

## Agent Roster

| Agent               | Role                                   | LLM                 | MCP Server | Tools                                            |
| ------------------- | -------------------------------------- | ------------------- | ---------- | ------------------------------------------------ |
| **Orchestrator**    | Routes requests, synthesizes responses | Qwen3-32B (local)   | —          | speak, express, look_at                          |
| **Email Agent**     | Read, search, draft emails             | Qwen3-32B (local)   | ms_graph   | MCP: read_emails, send_email, search_emails      |
| **Calendar Agent**  | View/create calendar events            | Qwen3-32B (local)   | ms_graph   | MCP: list_calendar_events, create_calendar_event |
| **Linear Agent**    | Manage issues and projects             | Qwen3-32B (local)   | linear     | MCP: list_my_issues, create_issue, update_issue  |
| **Fireflies Agent** | Search meeting transcripts             | Qwen3-32B (local)   | fireflies  | MCP: list_recent_meetings, search_transcripts    |
| **Vision Agent**    | Analyze camera feed                    | Qwen3-VL 4B (local) | —          | capture_frame, describe_scene                    |
| **General Agent**   | Conversation, general queries          | Qwen3-32B (local)   | —          | speak, express                                   |

## Intent Routing

User utterances are classified by the semantic router (nomic-embed-text V2) into one of 7 categories before hitting any LLM:

- `email` → Email Agent
- `calendar` → Calendar Agent
- `linear` → Linear Agent
- `fireflies` → Fireflies Agent
- `vision` → Vision Agent
- `general_chat` → General Agent
- `robot_control` → General Agent (with robot tools)

## Approval Gates

These actions require explicit user confirmation before execution:

- `send_email` — Sending any email
- `create_issue` — Creating Linear issues
- `create_calendar_event` — Scheduling calendar events

## LLM Fallback Chain

1. **Qwen3-32B** (local MLX) — 90% of requests
2. **Gemini 2.5 Flash** (cloud) — Complex reasoning fallback
3. **Claude Sonnet 4.5** (API) — Hardest tasks only
