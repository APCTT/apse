const test = require("node:test");
const assert = require("node:assert/strict");

const {
  escapeHtml,
  safeExternalUrl,
} = require("../frontend/security-utils.js");

test("escapeHtml neutralizes markup and attribute delimiters", () => {
  assert.equal(
    escapeHtml('<img src=x onerror="alert(1)">'),
    "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
  );
});

test("safeExternalUrl allows only ordinary HTTP(S) URLs", () => {
  assert.equal(safeExternalUrl("javascript:alert(1)"), "");
  assert.equal(safeExternalUrl("data:text/html,<script>alert(1)</script>"), "");
  assert.equal(safeExternalUrl("https://user:pass@example.com/record"), "");
  assert.equal(
    safeExternalUrl('https://example.com/" onmouseover="alert(1)'),
    "https://example.com/%22%20onmouseover=%22alert(1)"
  );
  assert.equal(
    safeExternalUrl("https://example.com/record?id=10"),
    "https://example.com/record?id=10"
  );
});
