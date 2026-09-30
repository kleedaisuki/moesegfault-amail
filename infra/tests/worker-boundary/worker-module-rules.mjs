/** Interpret worker-build's .js glue as ESM while retaining .mjs and Wasm. */
export const workerModuleRules = [
  { type: "ESModule", include: ["**/*.mjs", "**/*.js"] },
  { type: "CompiledWasm", include: ["**/*.wasm"] },
];
