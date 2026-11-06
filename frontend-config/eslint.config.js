// @ts-check
// The package lints itself with its own configuration. Its sources and tests run in Node.
import { base, node } from "./src/eslint.js";

export default [...base(), node(["src/**/*.js", "test/**/*.js"])];
