# AGENTS.md

This file provides instructions for AI coding agents working on this project.

## Project Context

**Type**: Personal assistant agent for Reachy Mini robot
**Stack**: Python 3.12 (FastAPI) + SvelteKit 5 (TypeScript) monorepo
**Package Manager**: pnpm (frontend), uv (backend)

## Quick Reference

### Essential Commands

```bash
# Frontend
cd frontend && pnpm install
cd frontend && pnpm dev
cd frontend && pnpm lint
cd frontend && pnpm test

# Backend (uv)
cd backend && uv sync --dev
cd backend && uv run uvicorn src.main:app --reload --port 8080
cd backend && uv run ruff check src/ tests/
cd backend && uv run mypy src/
cd backend && uv run pytest
```

### File Locations

- Frontend source: `frontend/src/`
- Backend source: `backend/src/`
- Backend tests: `backend/tests/`
- Config: `backend/configs/default.yaml`
- CI/CD: `.github/workflows/`
- Git hooks: `.husky/`

## Code Patterns

### Python (Backend)

```python
# Use future annotations and strict typing
from __future__ import annotations
from typing import Any

async def process_request(data: dict[str, Any]) -> str:
    """Process incoming request with clear docstring."""
    result = await some_async_operation(data)
    return result
```

### TypeScript/Svelte (Frontend)

```typescript
// Use Svelte 5 runes
let count = $state(0);
let doubled = $derived(count * 2);

// Use $props() for component props
interface Props {
  title: string;
}
let { title }: Props = $props();
```

### Integration Plugin Pattern

```python
class MyIntegration(Integration):
    name = "my_integration"
    description = "What this integration does"

    async def setup(self, config: dict[str, Any]) -> bool: ...
    async def get_tools(self) -> list[dict[str, Any]]: ...
    async def execute_tool(self, tool_name: str, args: dict[str, Any]) -> str: ...
    async def teardown(self) -> None: ...
```

## Workflow

### Before Making Changes

1. Understand the monorepo structure (backend/ and frontend/)
2. Check existing patterns in the relevant workspace
3. Review related tests

### After Making Changes

1. Backend: `ruff check`, `mypy`, `pytest`
2. Frontend: `pnpm lint`, `pnpm test`
3. Add tests for new functionality

### Commit Format

```
type: description

Types: feat, fix, chore, refactor, docs, test, ci, perf
```

## Boundaries

### Safe Actions

- Reading and analyzing code
- Running lint, type-check, test commands
- Modifying source files in `backend/src/` or `frontend/src/`
- Creating/modifying test files

### Require Approval

- Adding new dependencies
- Modifying config files
- Changing CI/CD workflows
- Creating new integration plugins

### Forbidden Actions

- Committing secrets or .env files
- Pushing directly to main
- Disabling type checking
- Removing tests
