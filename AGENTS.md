# AGENTS.md

This file provides instructions for AI coding agents working on this project.

## Project Context

**Type**: Venture startup template
**Stack**: Next.js 14, TypeScript, Supabase, Vercel, Tailwind CSS
**Package Manager**: pnpm (required)
**Node Version**: 20.x

## Quick Reference

### Essential Commands

```bash
pnpm install           # Install dependencies
pnpm lint              # Check code quality
pnpm type-check        # Validate TypeScript
pnpm test              # Run unit tests
pnpm changeset         # Create version changeset
```

### File Locations

- Source code: `src/`
- Tests: `src/**/__tests__/` or `*.test.ts`
- Config: Root directory (`*.config.{js,ts,json}`)
- Documentation: `docs/`
- CI/CD: `.github/workflows/`
- Git hooks: `.husky/` (pre-commit, pre-push, commit-msg)
- Local CI config: `.actrc`, `.actignore`, `.secrets` (gitignored)
- Secret scanning: `.gitleaks.toml`

## Code Patterns

### TypeScript

```typescript
// ✅ Strict types, explicit return types for public APIs
export function processData(input: InputType): OutputType {
  return transform(input);
}

// ✅ Use type inference for internal/obvious cases
const items = [1, 2, 3];
const doubled = items.map((x) => x * 2);
```

### Testing

```typescript
// ✅ Descriptive test names, AAA pattern
describe("functionName", () => {
  it("should return expected result when given valid input", () => {
    // Arrange
    const input = createTestInput();

    // Act
    const result = functionName(input);

    // Assert
    expect(result).toEqual(expectedOutput);
  });
});
```

### Error Handling

```typescript
// ✅ Explicit error handling, no silent failures
try {
  const result = await riskyOperation();
  return { success: true, data: result };
} catch (error) {
  console.error("Operation failed:", error);
  return { success: false, error: "Operation failed" };
}
```

## Workflow

### Before Making Changes

1. Understand existing patterns in the codebase
2. Check for similar implementations to follow
3. Review relevant tests for expected behavior

### After Making Changes

1. Run `pnpm lint` - fix all issues
2. Run `pnpm type-check` - fix all errors
3. Run `pnpm test` - ensure all pass
4. Add tests for new functionality
5. Create changeset if user-facing: `pnpm changeset`

### Commit Format

```
type: description

Types: feat, fix, chore, refactor, docs, test, ci, perf
Examples:
- feat: add user profile validation
- fix: resolve null pointer in auth flow
- chore: update dependencies
```

### Git Hooks (automated)

- **pre-commit**: Runs Gitleaks secret scan + lint-staged (ESLint, Prettier)
- **pre-push**: Runs GitHub Actions locally via act (if Docker + act installed)
- **commit-msg**: Validates commit message format via commitlint

Skip hooks if needed:

```bash
SKIP=gitleaks git commit -m "msg"   # Skip secret scan
SKIP=act git push                    # Skip local CI
```

## Boundaries

### Safe Actions (no approval needed)

- Reading and analyzing code
- Running lint, type-check, test commands
- Creating/modifying source files in `src/`
- Creating/modifying test files
- Formatting code with Prettier

### Require Approval

- Adding new npm dependencies
- Modifying config files (`*.config.*`, `tsconfig.json`)
- Changing CI/CD workflows (`.github/workflows/`)
- Modifying `package.json` scripts
- Creating new root-level files

### Forbidden Actions

- Committing to `main` branch directly
- Modifying `.env` files or committing secrets
- Disabling TypeScript strict mode
- Removing or skipping tests
- Using `npm` or `yarn` instead of `pnpm`
- Adding `@ts-ignore` without justification comment

## Common Tasks

### Add a New Utility Function

1. Create file in `src/lib/[name].ts`
2. Create test in `src/lib/__tests__/[name].test.ts`
3. Export from `src/lib/index.ts` if needed
4. Run validation: `pnpm lint && pnpm type-check && pnpm test`

### Fix a Bug

1. Write failing test that reproduces the bug
2. Implement the fix
3. Verify test passes
4. Run full validation suite
5. Create changeset: `pnpm changeset` (select `patch`)

### Add a New Feature

1. Create feature branch from `dev`
2. Implement with tests
3. Run full validation
4. Create changeset: `pnpm changeset` (select `minor`)
5. Create PR using template

## Dependencies

### Current Dev Dependencies

- TypeScript, ESLint, Prettier (code quality)
- Vitest, Testing Library (testing)
- Husky, lint-staged, commitlint (git hooks)
- Changesets (versioning)
- Gitleaks (secret scanning)

### Optional External Tools

- **act** + **Docker**: Local GitHub Actions simulation (pre-push hook)
- Install: `brew install act` (macOS), requires Docker Desktop

### Adding Dependencies

Before adding a new dependency:

1. Check if functionality exists in current deps
2. Evaluate bundle size impact
3. Check maintenance status and security
4. Prefer well-maintained, typed packages
