/** @type {import('lint-staged').Config} */
const config = {
  // TypeScript/JavaScript files - lint then format
  "*.{js,jsx,ts,tsx}": ["eslint --fix", "prettier --write"],

  // Styles
  "*.{css,scss}": ["prettier --write"],

  // JSON, Markdown, etc.
  "*.{json,md,mdx,yml,yaml}": ["prettier --write"],
};

export default config;
