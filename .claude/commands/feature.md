---
description: Create a GitHub issue from a feature request with codebase research
model: opus
---

# Feature Request → GitHub Issue

You are tasked with turning a feature request into a well-structured GitHub issue. You'll research the codebase, ask clarifying questions, and create the issue with proper labels and structure.

## Initial Response

When this command is invoked:

1. **If an argument was provided** (e.g., `/feature add a mute button to the voice pipeline`):
   - Use that as the feature description
   - Begin the research process immediately

2. **If no argument was provided**, respond with:

```
What feature would you like to request? Describe it in plain language — I'll research the codebase, ask clarifying questions, and create a structured GitHub issue.
```

Then wait for the user's input.

## Process

### Step 1: Codebase Research

Once you have the feature description:

1. **Spawn parallel research agents** to understand the current state:
   - Use **codebase-locator** agent: "Find all files related to [feature area]. Include configs, source files, and tests."
   - Use **codebase-analyzer** agent: "Analyze how [relevant system] currently works. Identify integration points and patterns."

2. **Read key files** identified by the research agents to build full understanding.

3. **Determine affected components** — collect specific file paths that would need changes.

### Step 2: Clarifying Questions

Present your research findings and ask focused questions:

```
Based on my research, here's what I found:

**Current state:**
- [Finding with file:line reference]
- [Relevant pattern or constraint]

**Affected components:**
- `path/to/file.ext` — [why it's affected]
- `path/to/other.ext` — [why it's affected]

Before I create the issue, a few questions:
```

Use the AskUserQuestion tool to ask about:

- **Scope**: What's the minimum viable version of this feature?
- **Priority**: How urgent is this? (low / medium / high)
- **Constraints**: Any technical constraints or preferences?
- **Acceptance criteria**: What does "done" look like?

Ask only questions that your research couldn't answer. Skip questions where the answer is obvious.

### Step 3: Draft the Issue

Compose the issue with these sections:

```markdown
## Problem / Motivation

[Why this feature is needed — from the user's description]

## Proposed Solution

[What should be built — synthesized from user input and codebase research]

## Affected Components

- `path/to/file.ext` — [what changes here]
- `path/to/other.ext` — [what changes here]

## Acceptance Criteria

- [ ] [Specific, testable criterion]
- [ ] [Another criterion]
- [ ] [Edge case or constraint]

## Implementation Notes

[Hints from codebase research — patterns to follow, integration points, gotchas]
```

### Step 4: Review and Create

1. **Show the draft** to the user and ask for approval:

```
Here's the issue I'll create:

Title: [title]
Labels: [labels]

[full body]

Want me to create this issue, or would you like changes?
```

2. **After approval**, create the issue:

```bash
gh issue create --title "<title>" --body "<body>" --label "<label1>,<label2>"
```

3. **Return the issue URL** to the user.

## Label Auto-Assignment

Always include `enhancement`. Add additional labels based on content:

| If the feature mentions...                       | Add label  |
| ------------------------------------------------ | ---------- |
| voice, audio, mic, speaker, STT, TTS, whisper    | `voice`    |
| camera, vision, Gemini, see, look, image         | `vision`   |
| frontend, UI, dashboard, component, Svelte, page | `frontend` |
| API, endpoint, route, backend, FastAPI, server   | `backend`  |
| OpenClaw, Claude, tool, bridge, MCP, agent       | `bridge`   |

Before creating the issue, ensure the labels exist. If a label doesn't exist yet, create it:

```bash
gh label create "<label>" --description "<description>" --color "<hex>"
```

Use these colors:

- `enhancement`: `a2eeef`
- `voice`: `d4c5f9`
- `vision`: `f9d0c4`
- `frontend`: `0075ca`
- `backend`: `e4e669`
- `bridge`: `bfdadc`

## Important Guidelines

- **Don't skip research.** The value of this command is the codebase-aware context it adds.
- **Be specific in affected components.** Include real file paths with brief explanations.
- **Keep acceptance criteria testable.** Each criterion should be verifiable.
- **Don't over-scope.** If the feature is large, suggest breaking it into multiple issues.
- **Title should be concise and action-oriented.** Use imperative mood (e.g., "Add mute button to voice pipeline").
