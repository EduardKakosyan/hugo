/** @type {import('lint-staged').Config} */
const config = {
  "*.{json,md,mdx,yml,yaml}": ["prettier --write"],
};

export default config;
