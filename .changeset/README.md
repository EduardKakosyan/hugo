# Changesets

This project uses [changesets](https://github.com/changesets/changesets) for version management.

## Adding a Changeset

When you make a change that should be released:

```bash
pnpm changeset
```

Follow the prompts to:

1. Select the type of change (major/minor/patch)
2. Write a summary of the change

This creates a markdown file in `.changeset/` that will be consumed during release.

## When to Add a Changeset

- **patch**: Bug fixes, documentation updates
- **minor**: New features (backward compatible)
- **major**: Breaking changes

## When NOT to Add a Changeset

- CI/CD changes
- Test-only changes
- Internal refactoring with no user impact
