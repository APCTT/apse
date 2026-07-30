(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MergedPagination = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function normalizeTotal(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
  }

  /**
   * Build the references for one global page without loading all source data.
   *
   * The merged order is round-robin while a source still has results. When a
   * smaller source is exhausted, the remaining sources fill its slots. Each
   * reference points to the source-local offset that the caller must fetch.
   */
  function buildPagePlan(sourceTotals, sourceOrder, requestedPage, pageSize = 20) {
    const size = Math.max(1, Math.floor(Number(pageSize) || 20));
    const order = [...new Set(sourceOrder || [])];
    const totals = Object.fromEntries(
      order.map((id) => [id, normalizeTotal(sourceTotals?.[id])])
    );

    const totalAcrossSources = order.reduce((sum, id) => sum + totals[id], 0);
    const totalPages = Math.max(1, Math.ceil(totalAcrossSources / size));
    const numericPage = Math.max(1, Math.floor(Number(requestedPage) || 1));
    const page = Math.min(numericPage, totalPages);
    const start = (page - 1) * size;
    const end = Math.min(start + size, totalAcrossSources);

    const used = Object.fromEntries(order.map((id) => [id, 0]));
    const refs = [];
    let emitted = 0;

    while (emitted < end) {
      let progressed = false;

      for (const sourceId of order) {
        if (used[sourceId] >= totals[sourceId]) continue;

        if (emitted >= start) {
          refs.push({ sourceId, localOffset: used[sourceId] });
        }

        used[sourceId] += 1;
        emitted += 1;
        progressed = true;

        if (emitted >= end) break;
      }

      if (!progressed) break;
    }

    return { page, refs, totalAcrossSources, totalPages };
  }

  return { buildPagePlan };
});
