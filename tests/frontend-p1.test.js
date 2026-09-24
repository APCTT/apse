const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(root, "frontend/index.html"), "utf8");
const app = fs.readFileSync(path.join(root, "frontend/app.js"), "utf8");
const styles = fs.readFileSync(path.join(root, "frontend/styles.css"), "utf8");

test("search UI explains matching mode and offers a recovery action", () => {
  assert.match(html, /id="search-method-note"[^>]*role="status"/);
  assert.match(app, /No strong matches/);
  assert.match(app, /data-clear-query/);
  assert.match(app, /Weak suggestions were hidden/);
});

test("large filter groups use progressive disclosure and in-filter search", () => {
  assert.match(app, /previewLimit = 5/);
  assert.match(app, /Show all \$\{filteredOptions\.length\}/);
  assert.match(app, /class="facet-search"/);
});

test("mobile filter drawer exposes state and restores accessibility boundaries", () => {
  assert.match(html, /aria-controls="search-filters" aria-expanded="false"/);
  assert.match(app, /setElementInert\(els\.filters, !isOpen\)/);
  assert.match(app, /filterSheetReturnFocus\.focus\(\)/);
  assert.match(styles, /\.filter-close\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;/s);
});

test("mobile comparison switches from the wide table to field-by-field content", () => {
  assert.match(app, /compare-mobile-fields/);
  assert.match(app, /mobileField\("Summary", "summary", \{ collapsible: true \}\)/);
  assert.match(styles, /\.compare-table-wrap,\s*\.compare-scroll-hint\s*\{\s*display:\s*none;/s);
  assert.match(styles, /\.compare-mobile-fields\s*\{\s*display:\s*block;/s);
});
