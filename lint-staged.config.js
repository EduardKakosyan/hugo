/** @type {import('lint-staged').Config} */
const config = {
  // Frontend TypeScript/JavaScript/Svelte files
  "frontend/**/*.{js,ts,svelte}": ["pnpm --dir frontend exec eslint --fix", "pnpm --dir frontend exec prettier --write"],

  // Styles
  "frontend/**/*.css": ["pnpm --dir frontend exec prettier --write"],

  // Python files
  "backend/**/*.py": ["uv run --project backend ruff check --fix"],

  // JSON, Markdown, etc.
  "*.{json,md,mdx,yml,yaml}": ["pnpm --dir frontend exec prettier --write"],
};

export default config;
