# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HUGO is a fresh repository with CI/CD infrastructure in place. Project code has not yet been added.

## Infrastructure

- **CI/CD**: GitHub Actions workflow for secret scanning (gitleaks)
- **Git hooks**: Husky (commitlint, gitleaks pre-commit, act pre-push)
- **Commit format**: `type: description` (conventional commits via commitlint)
- **Formatting**: Prettier for JSON, Markdown, YAML
- **Package manager**: pnpm (root only)

## Commands

```bash
pnpm install              # Install dependencies
pnpm secrets:check        # Scan staged files for secrets
pnpm secrets:scan         # Full repo secret scan
```

## Git Workflow

**Commit Message Format (enforced by commitlint):**

- Format: `type: description` (lowercase, max 100 chars)
- Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`

## Boundaries

### Always Do

- Follow conventional commit format
- Use `pnpm` for package management

### Never Do

- Commit secrets, API keys, or .env files
