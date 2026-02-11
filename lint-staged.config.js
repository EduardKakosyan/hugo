/** @type {import('lint-staged').Config} */
const config = {
  "*.{json,md,mdx,yml,yaml}": ["prettier --write"],
  "*.py": ["ruff check --fix", "ruff format"],
};

export default config;
