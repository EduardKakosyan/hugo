---
description: Implement a GitHub issue with plan-driven development
model: opus
---

# Implement GitHub Issue

You are tasked with implementing a GitHub issue using plan-driven development. You'll read the issue, research the codebase, create an implementation plan, and execute it.

## Initial Response

When this command is invoked:

1. **If an issue number or URL was provided** (e.g., `/implement 42` or `/implement https://github.com/org/repo/issues/42`):
   - Extract the issue number
   - Begin immediately

2. **If no argument was provided**, respond with:

```
Which GitHub issue should I implement? Provide an issue number or URL.
```

Then wait for the user's input.

## Process

### Step 1: Read the Issue

Fetch the full issue details:

```bash
gh issue view <number> --json title,body,labels,number,url
```

Parse the issue body to extract:

- **Problem / Motivation**
- **Proposed Solution**
- **Affected Components** (file paths)
- **Acceptance Criteria**
- **Implementation Notes**

If the issue doesn't follow this structure, extract what you can and fill gaps with your own research.

### Step 2: Codebase Research

1. **Read all files mentioned** in the "Affected Components" section — read them fully, no limit/offset.

2. **Spawn parallel research agents** for deeper understanding:
   - Use **codebase-locator** agent to find additional related files not listed in the issue
   - Use **codebase-analyzer** agent to understand current implementation patterns in the affected areas
   - Use **codebase-pattern-finder** agent to find similar features we can model after

3. **Synthesize findings** — understand the full scope of changes needed.

### Step 3: Create a Branch

Create a feature branch from the current branch:

```bash
git checkout -b feat/<issue-number>-<short-kebab-description>
```

For example: `feat/42-add-mute-button`

### Step 4: Create the Implementation Plan

Write an initial plan to `thoughts/shared/plans/YYYY-MM-DD-issue-<number>-<description>.md`.

Pre-populate it with context from the issue:

- The issue's problem statement as the Overview
- Affected components as the Current State Analysis
- Acceptance criteria mapped to Success Criteria
- Implementation notes as starting points for the approach

Then follow the `/create_plan` process:

- Research thoroughly using parallel sub-tasks
- Present design options if there are meaningful trade-offs
- Get user approval on the plan structure
- Write detailed phases with specific file changes and success criteria
- Separate automated and manual verification

**IMPORTANT**: Read `.claude/commands/create_plan.md` and follow its full process. The plan must be complete and actionable before implementation begins.

### Step 5: Implement the Plan

Once the plan is approved, follow the `/implement_plan` process:

**IMPORTANT**: Read `.claude/commands/implement_plan.md` and follow its full process:

- Implement each phase fully before moving to the next
- Run success criteria checks after each phase
- Update checkboxes in the plan as you complete sections
- Pause for manual verification when required

### Step 6: Commit Changes

Follow the `/commit` process:

**IMPORTANT**: Read `.claude/commands/commit.md` and follow its process:

- Group related changes into logical commits
- Use descriptive commit messages referencing the issue (e.g., `feat: add mute button (#42)`)
- Never add co-author or Claude attribution

### Step 7: Create a Pull Request

Push the branch and create a PR linking back to the issue:

```bash
git push -u origin feat/<issue-number>-<short-description>
```

```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
## Summary

[1-3 bullet points describing what was implemented]

## Changes

[List of key changes with file paths]

## Test Plan

- [ ] [How to verify the changes work]
- [ ] [Edge cases to test]

Closes #<issue-number>
EOF
)"
```

Return the PR URL to the user.

## Important Guidelines

- **Follow existing patterns.** Match the codebase's style and conventions.
- **Don't skip the plan.** The plan is what makes implementation reliable.
- **Reference the issue.** Commits and the PR should reference the issue number.
- **Keep scope tight.** Only implement what the issue asks for. If you discover related work, suggest separate issues.
- **Pause when uncertain.** If the issue is ambiguous or the plan doesn't cover a case, ask the user rather than guessing.
