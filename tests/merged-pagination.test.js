const test = require("node:test");
const assert = require("node:assert/strict");
const { buildPagePlan } = require("../frontend/merged-pagination.js");

function collectAll(totals, order, pageSize = 20) {
  const first = buildPagePlan(totals, order, 1, pageSize);
  const refs = [];
  for (let page = 1; page <= first.totalPages; page += 1) {
    refs.push(...buildPagePlan(totals, order, page, pageSize).refs);
  }
  return refs;
}

test("does not drop the rounded-up slots from eight sources", () => {
  const order = ["a", "b", "c", "d", "e", "f", "g", "h"];
  const totals = Object.fromEntries(order.map((id) => [id, 6]));
  const refs = collectAll(totals, order);

  assert.equal(refs.length, 48);
  assert.equal(new Set(refs.map((ref) => `${ref.sourceId}:${ref.localOffset}`)).size, 48);
  for (const id of order) {
    assert.deepEqual(
      refs.filter((ref) => ref.sourceId === id).map((ref) => ref.localOffset),
      [0, 1, 2, 3, 4, 5]
    );
  }
});

test("fills the page after smaller sources are exhausted", () => {
  const totals = { a: 100, b: 5, c: 5 };
  const refs = collectAll(totals, ["a", "b", "c"]);

  assert.equal(refs.length, 110);
  assert.equal(buildPagePlan(totals, ["a", "b", "c"], 1).refs.length, 20);
  assert.equal(buildPagePlan(totals, ["a", "b", "c"], 6).refs.length, 10);
  assert.deepEqual(
    refs.filter((ref) => ref.sourceId === "a").map((ref) => ref.localOffset),
    Array.from({ length: 100 }, (_, index) => index)
  );
});

test("handles source page boundaries and clamps an out-of-range page", () => {
  const plan = buildPagePlan({ a: 45 }, ["a"], 2);
  assert.equal(plan.refs[0].localOffset, 20);
  assert.equal(plan.refs.at(-1).localOffset, 39);

  const last = buildPagePlan({ a: 45 }, ["a"], 999);
  assert.equal(last.page, 3);
  assert.deepEqual(last.refs.map((ref) => ref.localOffset), [40, 41, 42, 43, 44]);
});

test("ignores zero, negative, invalid, and duplicate source entries", () => {
  const plan = buildPagePlan(
    { a: 2, b: 0, c: -1, d: "not-a-number" },
    ["a", "b", "a", "c", "d"],
    1
  );
  assert.equal(plan.totalAcrossSources, 2);
  assert.deepEqual(plan.refs, [
    { sourceId: "a", localOffset: 0 },
    { sourceId: "a", localOffset: 1 },
  ]);
});
