const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "frontend/app.js"), "utf8");

test("result cards keep stable source facts and omit unavailable optional values", () => {
  assert.match(app, /fact\("Provider", provider/);
  assert.match(app, /fact\("Readiness", readiness/);
  assert.match(app, /fact\("Source date", sourceDate/);
  assert.match(app, /fact\("Data currency", currency/);
  assert.match(app, /translatable = false\) => value \?/);
});

test("result cards show translation provenance only when it exists", () => {
  assert.match(app, /Machine-translated from/);
  assert.doesNotMatch(app, /key details provided/);
  assert.doesNotMatch(app, /Meaning match/);
});

test("source authority is explained near results and the primary action is consistent", () => {
  assert.match(html, /id="results-trust-strip"[^>]*role="note"/);
  assert.match(html, /Open the source record to verify current details and availability/);
  assert.match(app, /Open source record ↗/);
});
