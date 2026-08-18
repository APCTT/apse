const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const frontend = path.join(__dirname, "..", "frontend");
const index = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
const terms = fs.readFileSync(path.join(frontend, "terms-of-use.html"), "utf8");
const privacy = fs.readFileSync(path.join(frontend, "privacy-notice.html"), "utf8");
const robots = fs.readFileSync(path.join(frontend, "robots.txt"), "utf8");
const sitemap = fs.readFileSync(path.join(frontend, "sitemap.xml"), "utf8");

test("home page exposes its preferred search identity", () => {
  assert.match(index, /<title>Asia-Pacific Technology Transfer Search \| APTG<\/title>/);
  assert.match(index, /<link rel="canonical" href="https:\/\/ap-tg\.net\/" \/>/);
  assert.match(index, /<meta property="og:url" content="https:\/\/ap-tg\.net\/" \/>/);
  assert.match(index, /<meta name="robots" content="index, follow, max-image-preview:large" \/>/);
});

test("WebSite structured data is valid and allowed by CSP", () => {
  const match = index.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  assert.ok(match);
  const schema = JSON.parse(match[1]);
  assert.equal(schema["@type"], "WebSite");
  assert.equal(schema.name, "Asia-Pacific Tech Gateway");
  assert.equal(schema.alternateName, "APTG");
  assert.equal(schema.url, "https://ap-tg.net/");

  const hash = crypto.createHash("sha256").update(match[1]).digest("base64");
  assert.ok(index.includes(`'sha256-${hash}'`));
});

test("legal pages remain crawlable but are excluded from search results", () => {
  assert.match(terms, /<meta name="robots" content="noindex, follow" \/>/);
  assert.match(privacy, /<meta name="robots" content="noindex, follow">/);
});

test("robots and sitemap identify only the canonical landing page", () => {
  assert.match(robots, /User-agent: \*/);
  assert.match(robots, /Allow: \//);
  assert.match(robots, /Sitemap: https:\/\/ap-tg\.net\/sitemap\.xml/);
  assert.match(sitemap, /<loc>https:\/\/ap-tg\.net\/<\/loc>/);
  assert.doesNotMatch(sitemap, /terms-of-use|privacy-notice/);
});
