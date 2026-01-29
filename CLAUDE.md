# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a venture startup template optimized for Next.js + Supabase + Vercel deployments. It provides pre-configured:

- Git hooks (Husky) for commit linting and formatting
- ESLint + Prettier for code quality
- Vitest for unit testing
- GitHub Actions for CI/CD
- Changesets for versioning
- Gitleaks for secret scanning

## Commands

```bash
# Package Management (ALWAYS use pnpm, NOT npm or yarn)
pnpm install          # Install dependencies
pnpm prepare          # Set up husky git hooks

# Code Quality
pnpm lint             # Run ESLint + Prettier check
pnpm lint:fix         # Fix lint issues automatically
pnpm type-check       # Run TypeScript compiler check

# Testing
pnpm test             # Run all tests once
pnpm test:watch       # Run tests in watch mode
pnpm test:coverage    # Run tests with coverage report

# Versioning
pnpm changeset        # Create a changeset for versioning

# Security
pnpm secrets:check    # Scan staged files for secrets
pnpm secrets:scan     # Scan entire codebase for secrets
```

## Git Workflow

**Branching Strategy:**

- `main` is protected - no direct pushes
- Create feature branches from `dev`
- Only `dev` merges into `main` via PR
- Branch naming: `feat/description`, `fix/description`, `chore/description`

**Commit Message Format (enforced by commitlint):**

- Format: `type: description` (lowercase, max 100 chars)
- Types: `feat`, `fix`, `chore`, `refactor`, `docs`, `test`, `ci`, `perf`
- Example: `feat: add user authentication`

**Before Committing:**

1. Run `pnpm lint` - fix any issues
2. Run `pnpm type-check` - fix any errors
3. Run `pnpm test` - ensure all pass
4. Create changeset if needed: `pnpm changeset`

**Git Hooks (automated):**

- `pre-commit`: Runs Gitleaks secret scan + lint-staged
- `pre-push`: Runs GitHub Actions locally via act (if installed)
- `commit-msg`: Validates commit message format

Skip hooks if needed: `SKIP=act git push` or `SKIP=gitleaks git commit -m "msg"`

## Code Style

**TypeScript Strict Mode**: Always enabled. No `any` without justification.

**Imports**: Use `@/` alias for src directory imports.

```typescript
// ✅ Good
import { utils } from "@/lib/utils";

// ❌ Bad
import { utils } from "../../../lib/utils";
```

**Testing Pattern**:

```typescript
import { describe, it, expect } from "vitest";

describe("ComponentName", () => {
  it("should do expected behavior", () => {
    // Arrange
    const input = "test";

    // Act
    const result = functionUnderTest(input);

    // Assert
    expect(result).toBe("expected");
  });
});
```

## Boundaries

### ✅ Always Do

- Use TypeScript strict mode
- Follow existing patterns in the codebase
- Add tests for new functionality
- Run lint/type-check/test before committing
- Use `pnpm` for package management
- Follow conventional commit format
- Create changeset for user-facing changes

### ⚠️ Ask First

- Adding new dependencies
- Changing configuration files (tsconfig, eslint, etc.)
- Modifying CI/CD workflows
- Changing project structure

### 🚫 Never Do

- Commit secrets, API keys, or .env files
- Push directly to `main` branch
- Use `any` type without explicit comment justification
- Disable ESLint rules without justification
- Skip tests for new features
- Use `npm` or `yarn` (use `pnpm`)

## Project Structure

```
/src
  /lib              # Utility functions
    /__tests__      # Tests alongside code
  /components       # React components (when Next.js added)
  /hooks            # Custom React hooks (when Next.js added)
/docs
  /adr              # Architecture Decision Records
/.github
  /workflows        # GitHub Actions
/.changeset         # Version changesets
```

## Adding New Features

1. Create feature branch from `dev`
2. Implement with tests
3. Run full validation: `pnpm lint && pnpm type-check && pnpm test`
4. Create changeset: `pnpm changeset`
5. Commit with conventional format
6. Create PR using template
