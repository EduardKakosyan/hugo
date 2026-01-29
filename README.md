# venture-template

A production-ready startup template optimized for Next.js + Supabase + Vercel with AI-assisted development in mind.

## Features

- **Code Quality**: ESLint + Prettier with auto-fix on commit
- **Type Safety**: TypeScript strict mode
- **Testing**: Vitest + React Testing Library
- **CI/CD**: GitHub Actions for PR validation
- **Local CI**: Pre-push hook runs GitHub Actions locally via [act](https://github.com/nektos/act)
- **Git Workflow**: Husky hooks + commitlint for consistent commits
- **Versioning**: Changesets for semantic versioning
- **Security**: Gitleaks secret scanning on every commit and push
- **AI-Ready**: CLAUDE.md + AGENTS.md for AI coding assistants

## Quick Start

```bash
# 1. Fork and clone this repository
git clone <your-fork-url>
cd venture-template

# 2. Install dependencies (requires pnpm)
pnpm install

# 3. Create dev branch
git checkout -b dev

# 4. Start building!
```

## Commands

| Command              | Description                 |
| -------------------- | --------------------------- |
| `pnpm install`       | Install dependencies        |
| `pnpm lint`          | Run ESLint + Prettier check |
| `pnpm lint:fix`      | Auto-fix lint issues        |
| `pnpm type-check`    | Run TypeScript validation   |
| `pnpm test`          | Run unit tests              |
| `pnpm test:watch`    | Run tests in watch mode     |
| `pnpm test:coverage` | Generate coverage report    |
| `pnpm changeset`     | Create version changeset    |
| `pnpm secrets:scan`  | Scan codebase for secrets   |

## Git Workflow

### Branching Strategy

```
main (protected)
  └── dev (integration)
       ├── feat/feature-name
       ├── fix/bug-description
       └── chore/task-description
```

- `main` is protected - no direct pushes
- Create feature branches from `dev`
- Merge to `dev` first, then `dev` → `main` via PR

### Commit Format

Commits are validated by commitlint. Format: `type: description`

| Type       | Description             |
| ---------- | ----------------------- |
| `feat`     | New feature             |
| `fix`      | Bug fix                 |
| `chore`    | Maintenance task        |
| `refactor` | Code refactoring        |
| `docs`     | Documentation only      |
| `test`     | Adding/updating tests   |
| `ci`       | CI/CD changes           |
| `perf`     | Performance improvement |

Examples:

```bash
git commit -m "feat: add user authentication"
git commit -m "fix: resolve login timeout issue"
git commit -m "chore: update dependencies"
```

### PR Workflow

1. Create feature branch from `dev`
2. Make changes with tests
3. Run validation: `pnpm lint && pnpm type-check && pnpm test`
4. Create changeset (if needed): `pnpm changeset`
5. Push and create PR
6. CI validates automatically
7. Get review and merge

## Project Structure

```
venture-template/
├── src/
│   └── lib/              # Utility functions
│       └── __tests__/    # Unit tests
├── docs/
│   └── adr/              # Architecture Decision Records
├── .github/
│   └── workflows/        # GitHub Actions
├── .husky/               # Git hooks (pre-commit, pre-push, commit-msg)
├── .changeset/           # Version changesets
├── .actrc                # act configuration for local CI
├── .actignore            # Files excluded from act container
├── .gitleaks.toml        # Secret scanning rules
├── .secrets.example      # Template for local act secrets
├── CLAUDE.md             # Claude Code instructions
├── AGENTS.md             # AI agent instructions
└── [config files]
```

## Adding Your Next.js App

This template is tooling-only. To add your Next.js application:

```bash
# Option 1: Create new Next.js app in this directory
pnpm create next-app . --typescript --tailwind --eslint --app --src-dir

# Option 2: Copy your existing Next.js app
# (merge package.json dependencies manually)
```

## Architecture Decisions

Major decisions are documented in `docs/adr/`. To add a new decision:

1. Copy the template: `cp docs/adr/TEMPLATE.md docs/adr/NNNN-title.md`
2. Fill in the details
3. Include in your PR

## CI/CD

GitHub Actions automatically run on PRs to `main` and `dev`:

- **Lint**: ESLint + Prettier validation
- **Type Check**: TypeScript compilation
- **Test**: Vitest unit tests
- **Secret Scan**: Gitleaks secret detection
- **Changeset Check**: Warns if no changeset for versioned changes

### Local CI Testing with act (Optional)

This template includes a **pre-push hook** that automatically runs GitHub Actions locally using [nektos/act](https://github.com/nektos/act) before pushing. This catches CI failures early, saving time and avoiding failed builds.

#### Setup

1. **Install Docker** (required):
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/) for macOS/Windows
   - `sudo apt install docker.io` for Linux

2. **Install act**:

   ```bash
   # macOS
   brew install act

   # Windows
   scoop install act
   # or: choco install act-cli

   # Linux
   curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
   ```

3. **Configure secrets** (optional, for full Gitleaks support):

   ```bash
   cp .secrets.example .secrets
   # Edit .secrets with your tokens
   ```

4. **First run** - act will prompt to select an image size:
   - Choose **medium** for good compatibility vs. download size
   - The `.actrc` file pre-configures sensible defaults

#### Usage

The pre-push hook runs automatically:

```bash
git push  # act runs CI checks before push
```

Manual commands:

```bash
# Run full CI workflow
act push

# Run specific job
act -j validate

# List available workflows
act -l

# Dry run (show what would run)
act -n
```

#### Skipping Local CI

If you need to bypass the local CI check:

```bash
SKIP=act git push
```

**Note**: act supports ~79% of GitHub Actions features. Some complex actions may behave differently locally. If local CI fails but you're confident the code is correct, you can skip and let GitHub Actions run the authoritative check.

## Security

### Secret Scanning

Every commit is scanned for secrets using [Gitleaks](https://github.com/gitleaks/gitleaks):

- API keys (Supabase, Vercel, Stripe, etc.)
- Authentication tokens
- Private keys
- High-entropy strings

**If blocked**: Remove the secret, use environment variables, and update `.env.example`.

**False positive?** Add `// gitleaks:allow` inline or update `.gitleaks.toml`.

### Environment Variables

- Use `.env.local` for local development (gitignored)
- Use `.env.example` to document required variables (committed)
- Never commit real secrets

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## AI Assistance

This template is optimized for AI-assisted development:

- **CLAUDE.md**: Instructions for Claude Code
- **AGENTS.md**: Vendor-neutral AI agent instructions

These files provide context, patterns, and boundaries to help AI assistants write high-quality code that matches project conventions.
