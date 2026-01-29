/** @type {import('lint-staged').Config} */
const config = {
  // Frontend TypeScript/JavaScript/Svelte files
  "frontend/**/*.{js,ts,svelte}": ["eslint --fix", "prettier --write"],

  // Styles
  "frontend/**/*.css": ["prettier --write"],

  // Python files
  "backend/**/*.py": ["uv run --project backend ruff check --fix"],

  // JSON, Markdown, etc.
  "*.{json,md,mdx,yml,yaml}": ["prettier --write"],
};

export default config;
