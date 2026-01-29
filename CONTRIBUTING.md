# Contributing

Thank you for contributing to this project!

## Development Setup

1. Fork the repository
2. Clone your fork: `git clone <your-fork-url>`
3. Install dependencies: `pnpm install`
4. Create a branch: `git checkout -b feat/your-feature`

### Optional: Local CI with act

This repository includes a pre-push hook that runs GitHub Actions locally using [act](https://github.com/nektos/act). This catches CI failures before pushing, saving time and avoiding failed builds.

**Setup:**

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (required for act)
2. Install act:
   ```bash
   brew install act        # macOS
   scoop install act       # Windows
   # See https://github.com/nektos/act#installation for Linux
   ```
3. (Optional) Copy secrets for full Gitleaks support:
   ```bash
   cp .secrets.example .secrets
   # Edit .secrets with your GitHub token
   ```

**Usage:**

The pre-push hook runs automatically on `git push`. If act or Docker isn't available, it will warn but allow the push to continue.

```bash
git push                  # Runs local CI automatically
SKIP=act git push         # Skip local CI if needed
act push -j validate      # Run manually
```

**Note:** act supports ~79% of GitHub Actions features. See README for more details.

## Code Standards

### Before Submitting

Run the full validation suite:

```bash
pnpm lint        # Must pass
pnpm type-check  # Must pass
pnpm test        # Must pass
```

### Code Style

- TypeScript strict mode is enforced
- ESLint + Prettier handle formatting
- Follow existing patterns in the codebase

### Testing

- Add tests for new functionality
- Update tests when changing behavior
- Aim for meaningful coverage, not 100%

### Commits

Follow conventional commit format:

```
type: description

Types: feat, fix, chore, refactor, docs, test, ci, perf
```

Examples:

- `feat: add export functionality`
- `fix: resolve race condition in auth`
- `test: add coverage for edge cases`

### Changesets

If your change affects users (new feature, bug fix, breaking change):

```bash
pnpm changeset
```

Select the appropriate bump type:

- `patch`: Bug fixes
- `minor`: New features (backward compatible)
- `major`: Breaking changes

## Pull Request Process

1. Create PR against `dev` branch (not `main`)
2. Fill out the PR template completely
3. Ensure CI passes
4. Request review
5. Address feedback
6. Squash and merge when approved

## Architecture Decisions

For significant technical decisions, create an ADR:

1. Copy template: `cp docs/adr/TEMPLATE.md docs/adr/NNNN-title.md`
2. Fill in context, decision, and consequences
3. Include ADR in your PR

## Questions?

Open an issue for questions or discussions.
