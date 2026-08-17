const test = require("node:test");
const assert = require("node:assert/strict");

const analytics = require("../frontend/analytics.js");

function installConsent(value) {
  global.localStorage = {
    getItem(key) {
      return key === analytics.CONSENT_KEY ? value : null;
    },
    setItem() {},
  };
}

test.afterEach(() => {
  delete global.localStorage;
  delete global.gtag;
});

test("query length is reduced to a non-identifying bucket", () => {
  assert.equal(analytics.queryLengthBucket(""), "0");
  assert.equal(analytics.queryLengthBucket("solar irrigation"), "1-20");
  assert.equal(analytics.queryLengthBucket("x".repeat(51)), "51-100");
  assert.equal(analytics.queryLengthBucket("x".repeat(220)), "200+");
});

test("events are not sent without analytics consent", () => {
  installConsent("denied");
  const calls = [];
  global.gtag = (...args) => calls.push(args);

  assert.equal(analytics.trackSearch("confidential prototype", "search_form"), false);
  assert.deepEqual(calls, []);
});

test("free-text searches are measured without sending the query", () => {
  installConsent("granted");
  const calls = [];
  global.gtag = (...args) => calls.push(args);

  assert.equal(
    analytics.trackSearch("confidential prototype", "search_form", { sectors: 2 }),
    true
  );
  assert.equal(calls[0][0], "event");
  assert.equal(calls[0][1], "aptg_search");
  assert.equal(calls[0][2].query_length_bucket, "21-50");
  assert.equal(calls[0][2].sector_filter_count, 2);
  assert.equal("search_term" in calls[0][2], false);
  assert.equal(JSON.stringify(calls[0]).includes("confidential prototype"), false);
});

test("only an approved suggested topic is sent as a search term", () => {
  installConsent("granted");
  const calls = [];
  global.gtag = (...args) => calls.push(args);

  analytics.trackSearch("Renewable energy", "suggested_topic");

  assert.equal(calls[0][1], "search");
  assert.equal(calls[0][2].search_term, "renewable energy");
});

test("an approved phrase typed as free text is still not sent", () => {
  installConsent("granted");
  const calls = [];
  global.gtag = (...args) => calls.push(args);

  analytics.trackSearch("Renewable energy", "search_form");

  assert.equal(calls[0][1], "aptg_search");
  assert.equal("search_term" in calls[0][2], false);
});
