const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);
const API_BASE = LOCAL_HOSTS.has(window.location.hostname)
  ? "http://127.0.0.1:8000/api/v1"
  : "https://apsei-api.onrender.com/api/v1";
const {
  escapeHtml,
  normalizeDisplayText,
  safeExternalUrl: safeUrl,
} = globalThis.AptgSecurity;

// Runtime state — sources populated on init, technologies fetched on each search
let sourcesCache = [];
let sectorOptionsCache = [];

const GLOBAL_PAGE_SIZE = 20;

const DBTYPE_OPTIONS = [
  { value: "Metadata search", label: "Full technology listings" },
  { value: "Search redirect", label: "External search redirect" },
];

// Only these editorially approved topics are eligible for aggregate counting.
// Arbitrary text entered by users is never sent to the analytics endpoint.
const TRACKED_TOPIC_ALIASES = new Set([
  "climate resilience",
  "climate adaptation",
  "renewable energy",
  "ai",
  "artificial intelligence",
  "agriculture",
  "agricultural technology",
  "water",
  "water treatment",
  "health technology",
  "healthcare technology",
  "health care technology",
]);

const state = {
  query: "",
  countries: [],
  sectors: [],
  databaseTypes: [],
  sources: [],
  resultsView: "list",
  mergedPage: 1,
};

const FILTER_STATE_KEYS = ["countries", "sectors", "databaseTypes", "sources"];

const els = {
  form: document.querySelector("#search-form"),
  input: document.querySelector("#search-input"),
  results: document.querySelector("#results-container"),
  title: document.querySelector("#results-title"),
  summary: document.querySelector("#results-summary"),
  countryMs: document.querySelector("#country-multiselect"),
  sectorMs: document.querySelector("#sector-multiselect"),
  dbtypeMs: document.querySelector("#dbtype-multiselect"),
  sourceMs: document.querySelector("#source-multiselect"),
  clear: document.querySelector("#clear-filters"),
  filters: document.querySelector(".filters"),
  statsBar: document.querySelector("#global-stats-bar"),
  activeFilters: document.querySelector("#active-filters"),
  resetFilters: document.querySelector(".reset-filters"),
  filterBackdrop: document.querySelector(".filter-backdrop"),
  mobileFilterCount: document.querySelector(".mobile-filter-count"),
  app: document.querySelector(".apse"),
};

// ── Facet filter groups ──────────────────────────────────────────────────────

const multiselectInstances = [];

function initMultiselect(containerEl, options, getSelected, onChange, { defaultOpen = false } = {}) {
  let isOpen = defaultOpen;
  const groupLabel = containerEl.previousElementSibling?.textContent?.trim() || "Filter";

  function render() {
    const selected = getSelected();

    containerEl.innerHTML = `
      <button type="button" class="facet-group-toggle" aria-expanded="${isOpen}">
        <span>${escapeHtml(groupLabel)}${selected.length ? ` <strong>${selected.length}</strong>` : ""}</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg>
      </button>
      <div class="facet-options" ${isOpen ? "" : "hidden"}>
        ${options.map((o) => `
          <label class="facet-option">
            <span>
              <input type="checkbox" value="${escapeHtml(o.value)}" ${selected.includes(o.value) ? "checked" : ""}>
              <span>${escapeHtml(o.label)}</span>
            </span>
            ${Number.isFinite(o.count)
              ? `<small>${o.count.toLocaleString()}</small>`
              : `<small class="facet-availability" aria-label="Available. This source is connected, but its results cannot be counted in advance." title="Source available — count not available in advance."><span aria-hidden="true"></span></small>`}
          </label>`).join("")}
      </div>`;

    containerEl.querySelector(".facet-group-toggle").addEventListener("click", () => {
      isOpen = !isOpen;
      render();
    });

    containerEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const next = [...containerEl.querySelectorAll('input[type="checkbox"]:checked')].map((x) => x.value);
        onChange(next);
        render();
      });
    });
  }
  render();
  containerEl._render = render;
  containerEl._setOptions = (nextOptions) => {
    options = nextOptions;
    render();
  };
  multiselectInstances.push(containerEl);
}

function syncFacetControls() {
  multiselectInstances.forEach((container) => container._render?.());
}

// ── Helpers (unchanged) ──────────────────────────────────────────────────────

const statusClass = (status) => {
  if (status === "Metadata search") return "status-metadata";
  if (status === "Search redirect") return "status-redirect";
  return "status-listed";
};

const sourceInitials = (name) =>
  name
    .split(" ")
    .filter((word) => word.length > 3)
    .slice(0, 2)
    .map((word) => word[0])
    .join("");

function flagForCountry(country, source) {
  if (country === source.country) return (SOURCE_DETAIL[source.id] || {}).flag || "";
  const matchingSource = sourcesCache.find((candidate) =>
    candidate.country === country && (SOURCE_DETAIL[candidate.id] || {}).flag
  );
  return matchingSource ? SOURCE_DETAIL[matchingSource.id].flag : "";
}

// ── Render functions ──────────────────────────────────────────────────────────

// Technology fields come from crawled external sources, not from us — never
// trust them into innerHTML unescaped (a scraped title/summary containing
// "<img onerror=...>" would otherwise execute in every visitor's browser).
function formatPatentLabel(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/(^|[\s-])\S/g, (letter) => letter.toUpperCase());
}

function patentTechnologyCard(technology, source) {
  const cardCountry = technology.country || source.country;
  const flag = flagForCountry(cardCountry, source);
  const url = safeUrl(technology.url);
  const patentType = formatPatentLabel(technology.patent_type);
  const patentStatus = formatPatentLabel(technology.dev_status);
  const visibleMeta = [
    technology.reference_id ? `Application ${technology.reference_id}` : "",
    patentType ? `${patentType} patent` : "",
    patentStatus ? `Status: ${patentStatus}` : "",
  ].filter(Boolean);
  const detailRows = [
    ["Application number", technology.reference_id],
    ["Patent type", patentType],
    ["Filing date", technology.reg_date],
    ["Earliest priority", technology.priority_date],
    ["Patent status", patentStatus],
  ]
    .filter(([, value]) => value)
    .map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value">${escapeHtml(value)}</span>
      </div>`)
    .join("");

  return `
    <article class="technology-card patent-record-card" data-tech-id="${escapeHtml(technology.id)}">
      <div class="card-top-row">
        <div class="card-context">
          <span class="card-sector">Patent record</span>
          <span class="card-country">${flag} ${escapeHtml(cardCountry)}</span>
        </div>
        <span class="card-source-pill" title="${escapeHtml(source.name)}">${escapeHtml(source.name)}</span>
      </div>
      <h4 class="card-title">${escapeHtml(technology.title)}</h4>
      ${technology.org_name ? `
        <p class="patent-applicant">
          <span>Applicant</span>
          ${escapeHtml(technology.org_name)}
        </p>` : ""}
      ${visibleMeta.length ? `
        <div class="card-details patent-card-meta">
          ${visibleMeta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
        </div>` : ""}
      <div class="card-footer">
        ${detailRows ? `
          <details class="card-detail-disclosure">
            <summary>Patent details</summary>
            <div class="card-detail-panel">${detailRows}</div>
          </details>` : "<span></span>"}
        <div class="card-actions">
          ${url ? `<a class="button button-primary card-external-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">View patent record ↗</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

function technologyCard(technology, source) {
  if (technology.source_id === "ip_australia") {
    return patentTechnologyCard(technology, source);
  }

  const keywords = technology.keywords.slice(0, 3);
  const sectorCodes = technology.sector_codes || [];
  const sectorLabels = technology.sector_labels || [];
  const selectedSectorCode = sectorCodes.find((code) =>
    state.sectors.some((selected) => code === selected || code.startsWith(`${selected}.`))
  );
  const sectorIndex = selectedSectorCode ? sectorCodes.indexOf(selectedSectorCode) : 0;
  const sectorLabel = sectorLabels[sectorIndex] || technology.sector;
  const additionalSectorCount = Math.max(0, sectorLabels.length - 1);
  const sectorDisplay = sectorLabel
    ? `${escapeHtml(sectorLabel)}${additionalSectorCount ? ` +${additionalSectorCount}` : ""}`
    : escapeHtml(technology.sector);
  const allSectors = sectorLabels.join(", ");

  const detailRows = [
    ["Organisation",      technology.org_name],
    ["Sectors",           allSectors],
    ["Source category",   technology.source_sector],
    ["Sub-sector",        technology.sub_sector],
    ["Registered",        technology.reg_date],
  ]
    .filter(([, v]) => v)
    .map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value detail-translatable">${escapeHtml(value)}</span>
      </div>`)
    .join("");

  const needsTranslation = technology.language === "Korean";
  const cardCountry = technology.country || source.country;
  const flag = flagForCountry(cardCountry, source);
  const url = safeUrl(technology.url);
  const quickMeta = [
    technology.dev_status,
  ].filter(Boolean);

  return `
    <article class="technology-card" data-tech-id="${escapeHtml(technology.id)}" ${needsTranslation ? 'data-needs-translation="true"' : ""}>
      <div class="card-top-row">
        <div class="card-context">
          <span class="card-sector">${sectorDisplay}</span>
          <span class="card-country">${flag} ${escapeHtml(cardCountry)}</span>
        </div>
        <span class="card-source-pill" title="${escapeHtml(source.name)}">${escapeHtml(source.name)}</span>
      </div>
      <h4 class="card-title">${escapeHtml(technology.title)}</h4>
      <p class="card-summary">${escapeHtml(technology.summary) || "No summary available."}</p>
      ${keywords.length ? `
        <div class="card-keywords">
          ${keywords.map((k) => `<span class="keyword-tag">${escapeHtml(k)}</span>`).join("")}
        </div>` : ""}
      ${quickMeta.length ? `
        <div class="card-details">
          ${quickMeta.map((value) => `<span>${escapeHtml(value)}</span>`).join("")}
        </div>` : ""}
      <div class="card-footer">
        ${detailRows ? `
          <details class="card-detail-disclosure">
            <summary>More details</summary>
            <div class="card-detail-panel">${detailRows}</div>
          </details>` : "<span></span>"}
        <div class="card-actions">
          ${url ? `<a class="button button-primary card-external-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${technology.source_id === "ip_australia" ? "View patent source ↗" : "View original source ↗"}</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

// Google's public translate endpoint (same service backing the page-wide
// Google Translate widget) — no API key needed. Long text gets split into
// multiple chunks in the response, which we rejoin.
async function translateText(text) {
  if (!text || text.trim().length < 2) return text;
  const url = `https://translate.googleapis.com/translate_a/single?client=gtx&sl=ko&tl=en&dt=t&q=${encodeURIComponent(text.slice(0, 500))}`;
  const r = await fetch(url);
  const data = await r.json();
  return (data[0] || []).map((chunk) => chunk[0]).join("") || text;
}

// Korean NTB cards are auto-translated to English on render — no manual
// "Translate to English" button. Silent unless it fails.
async function autoTranslateCard(card) {
  const titleEl = card.querySelector(".card-title");
  const summaryEl = card.querySelector(".card-summary");
  const sectorEl = card.querySelector(".card-sector");
  const tags = card.querySelectorAll(".keyword-tag");

  try {
    const [translatedTitle, translatedSummary] = await Promise.all([
      translateText(titleEl.textContent),
      translateText(summaryEl.textContent),
    ]);
    titleEl.textContent = translatedTitle;
    summaryEl.textContent = translatedSummary;
    if (sectorEl) translateText(sectorEl.textContent).then((t) => { sectorEl.textContent = t; });
    tags.forEach((tag) => translateText(tag.textContent).then((t) => { tag.textContent = t; }));
    card.querySelectorAll(".detail-translatable").forEach((el) => {
      translateText(el.textContent).then((t) => { el.textContent = t; });
    });
    card.classList.add("translated");
  } catch {
    card.classList.add("translation-failed");
  }
}

function autoTranslateVisibleCards() {
  document.querySelectorAll('[data-needs-translation="true"]:not(.translated):not(.translation-failed)')
    .forEach((card) => autoTranslateCard(card));
}

const REDIRECT_SOURCE_INFO = {
  wipo_patentscope: {
    size: "128M+ patents",
    coverage: "International patent applications from 150+ countries via the PCT system.",
    cards: [
      {
        title: "International Patent Applications (PCT)",
        sector: "Patents",
        org: "World Intellectual Property Organization",
        country: "International",
        description: "Search PCT applications and national patents across Asia-Pacific member states including Japan, Korea, China, India, Australia, and 145+ other countries.",
      },
      {
        title: "Asia-Pacific Technology Filings",
        sector: "Patents — AP Region",
        org: "WIPO PATENTSCOPE",
        country: "Asia-Pacific",
        description: "Filter by Asia-Pacific offices (JP, KR, CN, IN, AU, SG, TH, VN and more) to find regionally relevant technology filings.",
      },
    ],
  },
};

function buildRedirectUrl(source, query) {
  const q = encodeURIComponent(query || "");
  if (source.id === "wipo_patentscope" && q) {
    return `https://patentscope.wipo.int/search/en/result.jsf?query=${q}`;
  }
  return source.url;
}

function redirectSourceBlock(source) {
  const info = REDIRECT_SOURCE_INFO[source.id];
  const sourceId = escapeHtml(source.id);
  const sourceName = escapeHtml(source.name);
  const sourceCountry = escapeHtml(source.country);
  const redirectUrl = safeUrl(buildRedirectUrl(source, state.query));
  const content = `<div class="technology-list redirect-technology-list view-grid">
        ${info ? info.cards.map((card) => `
          <article class="technology-card external-card">
            <div class="card-top-row">
              <div class="card-context">
                <span class="card-sector">${escapeHtml(card.sector)}</span>
                <span class="card-country">${escapeHtml(card.country)}</span>
              </div>
              <span class="card-source-pill">${sourceName}</span>
            </div>
            <h4 class="card-title">${escapeHtml(card.title)}</h4>
            <p class="card-summary">${escapeHtml(card.description)}</p>
            <div class="card-footer">
              <span class="redirect-card-organisation">${escapeHtml(card.org)}</span>
              <div class="card-actions">
                ${redirectUrl ? `<a class="button button-primary card-external-link"
                   href="${escapeHtml(redirectUrl)}"
                   target="_blank" rel="noopener noreferrer">
                  Search on ${sourceName}&nbsp; →
                </a>` : ""}
              </div>
            </div>
          </article>`).join("") : ""}
      </div>`;

  return `
    <section class="redirect-source-section" data-source-id="${sourceId}">
      <header class="redirect-source-heading">
        <div>
          <span class="section-kicker">External patent search</span>
          <div class="redirect-source-title">
            <span class="source-initial" aria-hidden="true">${escapeHtml(sourceInitials(source.name))}</span>
            <div>
              <h3>${sourceName}</h3>
              <p>${sourceCountry}</p>
            </div>
          </div>
        </div>
        <div class="group-meta">
          <span class="result-count">${escapeHtml(info ? info.size : "External source")}</span>
          <span class="status ${statusClass(source.status)}">${escapeHtml(source.status)}</span>
        </div>
      </header>
      ${content}
    </section>`;
}

function renderPaginationBar(current, total) {
  if (total <= 1) return "";
  const btns = [];
  const add = (p, label, active, disabled) =>
    `<button class="pagination-page-btn${active ? " active" : ""}"
      ${active ? 'aria-current="page"' : ""}
      ${disabled ? "disabled" : `data-merged-page="${p}"`}>${label}</button>`;

  btns.push(add(current - 1, "←", false, current === 1));
  btns.push(add(1, "1", current === 1, false));
  if (current > 4) btns.push(`<span class="pagination-ellipsis">…</span>`);

  const start = Math.max(2, current - 2);
  const end = Math.min(total - 1, current + 2);
  for (let p = start; p <= end; p++) btns.push(add(p, p, p === current, false));

  if (current < total - 3) btns.push(`<span class="pagination-ellipsis">…</span>`);
  if (total > 1) btns.push(add(total, total, current === total, false));
  btns.push(add(current + 1, "→", false, current === total));

  return `
    <div class="pagination-bar">
      ${btns.join("")}
      <span class="pagination-jump">
        <input class="pagination-jump-input" type="number" min="1" max="${total}"
          placeholder="${current}" aria-label="Go to page" data-page-total="${total}">
        <span class="pagination-jump-label">of ${total.toLocaleString()}</span>
      </span>
    </div>`;
}

// ── Merged round-robin grid ─────────────────────────────────────────────────
// Every metadata-search source paginates independently on the backend at
// page_size=20. The browser keeps a small per-search page cache, builds a
// deterministic round-robin plan from the source totals, and fetches only the
// backend pages referenced by the requested global page.

const sourcePageCache = new Map();
const SOURCE_PAGE_CACHE_LIMIT = 200;

function sourcePageCacheKey(sourceId, backendPage) {
  return JSON.stringify({
    sourceId,
    backendPage,
    query: state.query,
    countries: state.countries,
    sectors: state.sectors,
  });
}

async function fetchSourcePage(sourceId, backendPage) {
  const key = sourcePageCacheKey(sourceId, backendPage);
  if (sourcePageCache.has(key)) return sourcePageCache.get(key);

  const request = fetchResults({ source: sourceId, page: backendPage })
    .then((data) => {
      const result = {
        items: (data.results || []).filter((r) => r.source_id === sourceId),
        total: data.source_totals?.[sourceId] || 0,
        failed: (data.failed_sources || []).includes(sourceId),
      };
      // A transient upstream outage should be retried on the next render, not
      // pinned in the browser's page cache for the rest of the session.
      if (result.failed) sourcePageCache.delete(key);
      return result;
    })
    .catch((error) => {
      sourcePageCache.delete(key);
      throw error;
    });

  sourcePageCache.set(key, request);
  if (sourcePageCache.size > SOURCE_PAGE_CACHE_LIMIT) {
    sourcePageCache.delete(sourcePageCache.keys().next().value);
  }
  return request;
}

async function buildMergedPage(globalPage, activeIds) {
  if (!activeIds.length) {
    return { items: [], page: 1, totalAcrossSources: 0, totalPages: 1, failedSources: [] };
  }

  const sourceMap = Object.fromEntries(sourcesCache.map((s) => [s.id, s]));
  const firstPages = await Promise.all(activeIds.map((id) => fetchSourcePage(id, 1)));
  const sourceTotals = Object.fromEntries(
    activeIds.map((id, index) => [id, firstPages[index].total])
  );
  const failedSources = new Set(
    activeIds.filter((id, index) => firstPages[index].failed)
  );

  const plan = MergedPagination.buildPagePlan(
    sourceTotals,
    activeIds,
    globalPage,
    GLOBAL_PAGE_SIZE
  );

  const neededPageKeys = new Set();
  for (const ref of plan.refs) {
    const backendPage = Math.floor(ref.localOffset / 20) + 1;
    neededPageKeys.add(`${ref.sourceId}:${backendPage}`);
  }

  const pageData = new Map();
  await Promise.all([...neededPageKeys].map(async (pageKey) => {
    const separator = pageKey.lastIndexOf(":");
    const sourceId = pageKey.slice(0, separator);
    const backendPage = Number(pageKey.slice(separator + 1));
    const data = await fetchSourcePage(sourceId, backendPage);
    pageData.set(pageKey, data);
    if (data.failed) failedSources.add(sourceId);
  }));

  const items = [];
  for (const ref of plan.refs) {
    const backendPage = Math.floor(ref.localOffset / 20) + 1;
    const pageKey = `${ref.sourceId}:${backendPage}`;
    const tech = pageData.get(pageKey)?.items[ref.localOffset % 20];
    if (tech) {
      items.push({ tech, source: sourceMap[ref.sourceId] });
    } else {
      failedSources.add(ref.sourceId);
    }
  }

  return {
    items,
    page: plan.page,
    totalAcrossSources: plan.totalAcrossSources,
    totalPages: plan.totalPages,
    failedSources: [...failedSources],
  };
}

function renderMergedGrid(items) {
  if (!items.length) {
    // IP Australia's search API needs an actual keyword — selecting it alone
    // with no query silently returns nothing otherwise, which reads as broken.
    if (!state.query && state.sources.length === 1 && state.sources[0] === "ip_australia") {
      return `<div class="empty-state"><h3>Enter a keyword to search IP Australia</h3><p>IP Australia's search API requires a keyword — it can't list all patents at once. Type a term above to search it.</p></div>`;
    }
    const heading = state.query
      ? `No technologies available for "${escapeHtml(state.query)}"`
      : "No matching technologies found";
    return `<div class="empty-state"><h3>${heading}</h3><p>Try a broader keyword or clear one of the filters.</p></div>`;
  }
  return `<div class="technology-list merged-grid view-${state.resultsView}">
    ${items.map(({ tech, source }) => technologyCard(tech, source)).join("")}
  </div>`;
}

// ── API fetch layer ───────────────────────────────────────────────────────────

async function fetchSources() {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) throw new Error("Sources fetch failed");
  return res.json();
}

async function loadPopularSearches() {
  const container = document.querySelector("#popular-chips");
  const label = document.querySelector("#popular-searches-label");
  if (!container) return;
  try {
    const res = await fetch(`${API_BASE}/popular-searches`);
    if (!res.ok) throw new Error("Popular searches fetch failed");
    const data = await res.json();
    const topics = Array.isArray(data.topics) ? data.topics.slice(0, 6) : [];
    if (!topics.length) return;
    container.innerHTML = topics.map((topic) => `
      <button type="button" data-keyword="${escapeHtml(topic.query)}">${escapeHtml(topic.label)}</button>
    `).join("");
    const hasRecentActivity = topics.some((topic) => Number(topic.count) > 0);
    if (label) {
      label.textContent = hasRecentActivity
        ? `Popular searches · last ${Number(data.window_days) || 30} days`
        : "Suggested searches";
    }
  } catch {
    // Keep the editorial fallback already present in the HTML.
  }
}

function recordTrackedTopicSearch(query) {
  const normalized = normalizeDisplayText(query).trim().toLowerCase().replace(/\s+/g, " ");
  if (!TRACKED_TOPIC_ALIASES.has(normalized)) return;
  fetch(`${API_BASE}/search-events`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query: normalized }),
  }).catch(() => {});
}

async function fetchFacets() {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.countries.length) params.set("country", state.countries.join(","));
  if (state.sectors.length) params.set("sector", state.sectors.join(","));
  if (state.sources.length) params.set("source", state.sources.join(","));
  if (state.databaseTypes.length) params.set("database_type", state.databaseTypes.join(","));
  const res = await fetch(`${API_BASE}/facets?${params}`);
  if (!res.ok) throw new Error("Facets fetch failed");
  return res.json();
}

function updateFacetOptions(facets) {
  const countryOptions = (facets.countries || []).map((item) => ({
    value: item.value,
    label: item.label,
    count: item.count,
  }));
  const sectorOptions = (facets.sectors || []).map((item) => ({
    value: item.value,
    label: item.label,
    count: item.count,
  }));
  const sourceOptions = (facets.sources || []).map((item) => ({
    value: item.value,
    label: item.label,
    count: item.count,
  }));
  sectorOptionsCache = sectorOptions;
  if (countryOptions.length) els.countryMs._setOptions?.(countryOptions);
  els.sectorMs._setOptions?.(sectorOptions);
  if (sourceOptions.length) els.sourceMs._setOptions?.(sourceOptions);
}

async function refreshFacetCounts(token) {
  const facets = await fetchFacets();
  if (token !== renderResultsToken) return;
  updateFacetOptions(facets);
  renderActiveFilters();
}

// A sleeping, restarting, or freshly deployed backend can make the first
// request slow. Retry silently so the page self-heals instead of requiring
// the user to click "Clear filters" or reload manually.
async function withWakeupRetry(fn, { attempts = 6, delayMs = 6000, onRetry } = {}) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      if (i < attempts - 1) {
        onRetry?.(i + 1, attempts);
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }
  }
  throw lastErr;
}

async function fetchResults(overrides = {}) {
  const params = new URLSearchParams();
  const page = overrides.page || 1;
  const src  = overrides.source !== undefined ? overrides.source : state.sources.join(",");
  const excl = overrides.exclude;
  if (state.query)          params.set("q", state.query);
  if (state.countries.length) params.set("country", state.countries.join(","));
  if (state.sectors.length)   params.set("sector", state.sectors.join(","));
  if (src)            params.set("source", src);
  if (excl)           params.set("exclude", excl);
  if (page > 1)       params.set("page", page);
  const res = await fetch(`${API_BASE}/search?${params}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function updateStatsBar(totalTechs, totalSources, totalCountries) {
  if (!els.statsBar) return;
  els.statsBar.querySelector("#gsb-stat-techs").textContent = totalTechs.toLocaleString();
  els.statsBar.querySelector("#gsb-stat-sources").textContent = totalSources.toLocaleString();
  els.statsBar.querySelector("#gsb-stat-countries").textContent = totalCountries.toLocaleString();
  const label = els.statsBar.querySelector("#gsb-stat-techs-label");
  if (label) label.textContent = hasActiveSearch() ? "Matching records" : "Indexed records";
}

function hasActiveSearch() {
  return Boolean(
    state.query ||
    state.countries.length ||
    state.sectors.length ||
    state.databaseTypes.length ||
    state.sources.length
  );
}

function syncSearchMode() {
  els.app?.classList.toggle("has-active-search", hasActiveSearch());
  const activeFilterCount = FILTER_STATE_KEYS.reduce((total, key) => total + state[key].length, 0);
  if (els.mobileFilterCount) {
    els.mobileFilterCount.textContent = activeFilterCount;
    els.mobileFilterCount.hidden = activeFilterCount === 0;
  }
}

function renderActiveFilters() {
  if (!els.activeFilters) return;
  const sourceMap = Object.fromEntries(sourcesCache.map((source) => [source.id, source.name]));
  const sectorMap = Object.fromEntries(sectorOptionsCache.map((sector) => [sector.value, sector.label]));
  const items = [
    ...(state.query ? [{ type: "query", value: state.query, label: `Keyword: ${state.query}` }] : []),
    ...state.countries.map((value) => ({ type: "countries", value, label: value })),
    ...state.sectors.map((value) => ({ type: "sectors", value, label: sectorMap[value] || value })),
    ...state.databaseTypes.map((value) => ({ type: "databaseTypes", value, label: value })),
    ...state.sources.map((value) => ({ type: "sources", value, label: sourceMap[value] || value })),
  ];

  els.activeFilters.innerHTML = items.map((item) => `
    <button type="button" class="active-filter-chip" data-filter-type="${item.type}" data-filter-value="${escapeHtml(item.value)}">
      <span>${escapeHtml(item.label)}</span><span aria-hidden="true">×</span>
      <span class="visually-hidden">Remove filter</span>
    </button>
  `).join("");
  els.activeFilters.hidden = items.length === 0;
}

// Clickable source chips shown under the stats row — a visual alternative to
// the "Source platform" dropdown filter. Quick chips are single-select, while
// the dropdown supports selecting multiple sources.
function renderSourceChips() {
  const container = document.querySelector("#gsb-source-chips");
  if (!container || !sourcesCache.length) return;
  container.innerHTML = sourcesCache.map((s) => {
    const flag = (SOURCE_DETAIL[s.id] || {}).flag || "";
    const active = state.sources.includes(s.id);
    return `<button type="button" class="gsb-chip${active ? " active" : ""}" data-source="${escapeHtml(s.id)}" aria-pressed="${active}">
      <span aria-hidden="true">${flag}</span> ${escapeHtml(s.name)}
    </button>`;
  }).join("");
  container.querySelectorAll(".gsb-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.source;
      // Single-select: a chip means "show me this source" — clicking a
      // second one switches to it rather than adding to a combo, matching
      // how a source directory is browsed. Real multi-select combos are
      // still available via the Source platform dropdown filter.
      state.sources = state.sources.includes(id) ? [] : [id];
      state.mergedPage = 1;
      els.sourceMs._render?.();
      renderResults();
    });
  });
}

// Sources that back the merged, paginated grid (metadata-search sources).
// Korea NTB is excluded from the round-robin pool by default — a single
// unfiltered search against it takes up to 25s, which would stall every
// global page load. It's included automatically when explicitly filtered
// (by source or by country) and always counted toward the header total.
// The true set of metadata-search sources matching the active filters,
// excluding only redirect-only sources (e.g. WIPO) — used for the header's
// "N source platforms" count so it reflects real data sources, not the
// performance-trimmed subset actually fetched for the round-robin grid.
function getFilterableSourceIds() {
  const sourceMap = Object.fromEntries(sourcesCache.map((s) => [s.id, s]));
  if (state.databaseTypes.length && !state.databaseTypes.includes("Metadata search")) return [];

  let ids = sourcesCache
    .filter((s) => s.status === "Metadata search")
    .map((s) => s.id);

  if (state.sources.length) ids = ids.filter((id) => state.sources.includes(id));
  if (state.countries.length) {
    ids = ids.filter((id) =>
      sourceMap[id]?.multi_country || state.countries.includes(sourceMap[id]?.country)
    );
  }
  if (state.sectors.length) ids = ids.filter((id) => sourceMap[id]?.sector_filter_supported);

  return ids;
}

function getActiveMergeIds() {
  let ids = getFilterableSourceIds();

  // Korea NTB's external API takes up to 25s — excluded from the round-robin
  // pool unless explicitly requested, so it doesn't stall every page load.
  const explicitlyWantsNTB = state.sources.includes("korea_ntb") || state.countries.includes("Republic of Korea");
  if (!explicitlyWantsNTB) ids = ids.filter((id) => id !== "korea_ntb");

  // IP Australia's quick-search API requires a real query term — including it
  // in the round-robin denominator for a blank search wastes page capacity
  // since it always contributes 0 items.
  if (!state.query) ids = ids.filter((id) => id !== "ip_australia");

  return ids;
}

function getRedirectSources() {
  if (state.databaseTypes.length && !state.databaseTypes.includes("Search redirect")) return [];
  return sourcesCache.filter((s) =>
    s.status === "Search redirect" &&
    (!state.sources.length || state.sources.includes(s.id)) &&
    (!state.countries.length || state.countries.includes(s.country)) &&
    !state.sectors.length
  );
}

let lastActiveIds = [];
let renderResultsToken = 0;

function mergedGridHeader(activeIds, mergedPage, totalPages, totalAcrossSources) {
  return `
    <header class="group-header">
      <div class="group-source">
        <span class="source-initial" aria-hidden="true">ALL</span>
        <div>
          <h3>Search results</h3>
          <p>${activeIds.length} source platform${activeIds.length === 1 ? "" : "s"}</p>
        </div>
      </div>
      <div class="group-meta">
        <span class="result-count">Page ${mergedPage} of ${totalPages.toLocaleString()} · ${totalAcrossSources.toLocaleString()} matching records</span>
        <span class="status status-metadata">Metadata search</span>
      </div>
    </header>`;
}

async function renderResults() {
  // Rapid successive calls (e.g. clicking two source chips back-to-back) can
  // resolve out of order; only the most recent call is allowed to write to
  // the DOM, so a slow stale response can't clobber a newer one.
  const token = ++renderResultsToken;
  syncSearchMode();
  renderActiveFilters();
  refreshFacetCounts(token).catch(() => {});

  els.title.textContent = state.query ? `Results for "${state.query}"` : "Technology search results";
  els.summary.textContent = "Searching across source platforms…";
  els.results.innerHTML = `<div class="empty-state"><p>Loading results…</p></div>`;
  updateStatsBar(0, 0, 0);
  renderSourceChips();

  const filterableIds = getFilterableSourceIds();
  const activeIds = getActiveMergeIds();
  const redirectSources = getRedirectSources();
  lastActiveIds = activeIds;

  let merged;
  try {
    merged = await withWakeupRetry(() => buildMergedPage(state.mergedPage, activeIds), {
      onRetry: () => {
        if (token === renderResultsToken) {
          els.results.innerHTML = `<div class="empty-state"><p>Waking up the search service — this can take up to 30 seconds on first load…</p></div>`;
        }
      },
    });
  } catch {
    if (token === renderResultsToken) {
      els.results.innerHTML = `
        <div class="empty-state">
          <h3>Could not connect to the search service</h3>
          <p>The search service is temporarily unavailable. Please wait a moment and refresh.</p>
        </div>`;
    }
    return;
  }

  if (token !== renderResultsToken) return; // a newer call already started; discard this stale result
  state.mergedPage = merged.page;
  // The search request may have created and cached a semantic query vector.
  // Refresh once more so facet counts follow the same expanded result set.
  refreshFacetCounts(token).catch(() => {});

  // Blank state — no search term and no filters applied. Show only the
  // indexed source information (name, coverage, counts) rather than
  // flooding the page with an unrequested pile of technology cards.
  const isBlankState = !hasActiveSearch();

  if (isBlankState) {
    els.results.innerHTML = `
      <div class="empty-state browse-prompt browse-prompt-compact">
        <span class="browse-prompt-kicker">Ready to explore</span>
        <p>Enter a keyword above, choose a suggested search, or browse the <a href="#sources">source platforms</a>.</p>
      </div>`;
    els.summary.textContent = "Explore technology information indexed from source platforms.";
  } else {
    const redirectHtml = redirectSources.map(redirectSourceBlock).join("");
    const gridHtml = renderMergedGrid(merged.items);
    const paginationHtml = merged.items.length ? renderPaginationBar(merged.page, merged.totalPages) : "";
    const partialHtml = merged.failedSources.length
      ? `<p class="results-warning" role="status">Some source platforms could not be reached. The results shown are partial; please try again later.</p>`
      : "";

    els.results.innerHTML = `
      <div class="merged-grid-wrap">
        ${partialHtml}
        ${gridHtml}
        ${paginationHtml}
      </div>
      ${redirectHtml}`;
    autoTranslateVisibleCards();

    if (!merged.items.length) els.summary.textContent = "No results on this page — try adjusting your filters.";
  }

  const includesNTB = activeIds.includes("korea_ntb");
  const sourceMap = Object.fromEntries(sourcesCache.map((s) => [s.id, s]));
  const totalCountries = new Set(filterableIds.map((id) => sourceMap[id]?.country).filter(Boolean)).size;
  const totalVisibleSources = new Set([
    ...filterableIds,
    ...redirectSources.map((source) => source.id),
  ]).size;
  updateStatsBar(merged.totalAcrossSources, totalVisibleSources, totalCountries);
  if (!isBlankState) {
    els.title.textContent = state.query
      ? `${merged.totalAcrossSources.toLocaleString()} results for "${state.query}"`
      : `${merged.totalAcrossSources.toLocaleString()} matching records`;
    els.summary.textContent = `${totalVisibleSources.toLocaleString()} indexed source${totalVisibleSources === 1 ? "" : "s"} · ${totalCountries.toLocaleString()} countr${totalCountries === 1 ? "y" : "ies"}`;
  }

  // Fetch Korea NTB's live total in the background purely for the tech-count
  // total, when it matches the active filters but was trimmed from the
  // round-robin pool for performance. filterableIds.length already counts it
  // toward "N source platforms" above — this only adds its record count.
  const shouldCheckNTBSeparately = !includesNTB && filterableIds.includes("korea_ntb");
  if (shouldCheckNTBSeparately) {
    fetchResults({ source: "korea_ntb", page: 1 })
      .then((data) => {
        const ntbTotal = data.source_totals?.korea_ntb || 0;
        if (lastActiveIds !== activeIds) return; // a newer search superseded this one
        const combinedTotal = merged.totalAcrossSources + ntbTotal;
        updateStatsBar(combinedTotal, totalVisibleSources, totalCountries);
        if (hasActiveSearch()) {
          els.title.textContent = state.query
            ? `${combinedTotal.toLocaleString()} results for "${state.query}"`
            : `${combinedTotal.toLocaleString()} matching records`;
        }
      })
      .catch(() => {});
  }
}

async function changeMergedPage(page) {
  state.mergedPage = page;
  await renderResults();
  document.querySelector("#search-results").scrollIntoView({ behavior: "smooth", block: "start" });
}

window.changeMergedPage = changeMergedPage;

// Rich detail info per source — shown on the source cards page
const SOURCE_DETAIL = {
  apctt: {
    flag: "🌏",
    sizeLabel: "technology offers",
    description: "Technology offers submitted directly to APCTT and published in its official catalogue. APCTT reviews submitted information and, where needed, directly coordinates follow-up between relevant technology providers and interested parties.",
    coverage: "Asia and the Pacific — submissions from organizations offering technologies for transfer, cooperation, licensing, pilot deployment, or other forms of collaboration.",
    searchHint: "Search by title, organization, keyword, application area, or technology description. Open the original APCTT record for complete information and follow-up details.",
  },
  korea_ntb: {
    flag: "🇰🇷",
    size: "128,000+",
    sizeValue: 128000,
    sizeLabel: "technologies",
    description: "Korea's national repository for technology transfer offers from universities, research institutes, and public R&D institutions. Technologies span manufacturing, ICT, biotech, energy, and more.",
    coverage: "Republic of Korea — domestic technologies available for licensing, joint development, or transfer to domestic and international organizations.",
    searchHint: "Search in English — queries are automatically translated to Korean.",
  },
  wipo_patentscope: {
    flag: "🌏",
    size: "128M+",
    sizeLabel: "patents",
    description: "WIPO PATENTSCOPE provides access to international patent applications filed via the PCT system, as well as national patent collections from 50+ offices.",
    coverage: "Global — includes Asia-Pacific offices: JP, KR, CN, IN, AU, SG, TH, VN, PH, MY, ID, NZ and 140+ other countries.",
    searchHint: "Clicking 'Search on WIPO' will open PATENTSCOPE with your query pre-filled.",
  },
  ip_australia: {
    flag: "🇦🇺",
    size: "6,000+",
    sizeValue: 6000,
    sizeLabel: "patents",
    description: "Official metadata for Australian patent applications and grants from IP Australia. These records support prior-art and patent discovery; they do not by themselves indicate that a technology is offered for licensing or transfer.",
    coverage: "Australian patent jurisdiction — includes standard, provisional and innovation patent records, as well as PCT applications entering the national phase.",
    searchHint: "Search by title, applicant, inventor or keyword. Results show filing metadata and link to the official Australian Patent Search record for specifications and legal details.",
  },
  csir_india: {
    flag: "🇮🇳",
    size: "1,739",
    sizeValue: 1739,
    sizeLabel: "technologies",
    description: "India's Council of Scientific and Industrial Research (CSIR) technology transfer portal — spanning 30+ national laboratories across agriculture, food, health, energy, materials, ICT, and manufacturing.",
    coverage: "India — technologies from CSIR institutes available for licensing, joint development, and commercialisation by domestic and international organizations.",
    searchHint: "Search by technology name, application area, or CSIR institute. Each result links directly to the full technology profile.",
  },
  dost_tapi: {
    flag: "🇵🇭",
    size: "75",
    sizeValue: 75,
    sizeLabel: "technologies",
    description: "The DOST-TAPI Technology Transfer Portal lists technologies developed by Philippine government R&D institutes ready for commercialisation across 5 priority sectors.",
    coverage: "Philippines — technologies from DOST agencies covering agricultural productivity, healthcare, MSME competitiveness, ICT, and disaster resilience.",
    searchHint: "Search by technology name or application area. Each result links to the full DOST-TAPI technology profile.",
  },
  tech2biz: {
    flag: "🇹🇭",
    size: "645",
    sizeValue: 645,
    sizeLabel: "technologies",
    description: "Tech2Biz is Thailand's national technology matching platform, connecting researchers from NSTDA institutes and universities with investors and entrepreneurs seeking innovations for commercialisation.",
    coverage: "Thailand — technologies from NSTDA, universities, and public R&D institutes across agriculture, health, ICT, materials, food, energy, and manufacturing.",
    searchHint: "Search in English — titles have been translated from Thai. Use the Translate button on each card to read full descriptions in English.",
  },
  jst_japan: {
    flag: "🇯🇵",
    size: "303",
    sizeValue: 303,
    sizeLabel: "patents",
    description: "Japan Science and Technology Agency (JST) patent portfolio — patents from Japanese universities and public research institutes explicitly available for international licensing across 14 technology categories.",
    coverage: "Japan — patents from JST-funded research institutions covering biotech, materials, semiconductors, energy, medical devices, software, robotics, and more. Each patent links directly to Google Patents for full specifications.",
    searchHint: "Search by technology name, inventor, or category (e.g. 'BIOTECHNOLOGY', 'ENERGY/GREEN'). Licensing enquiries: license@jst.go.jp",
  },
  nrdc_india: {
    flag: "🇮🇳",
    size: "462",
    sizeValue: 462,
    sizeLabel: "technologies",
    description: "National Research Development Corporation (NRDC) technology portfolio — established 1953 under India's Department of Scientific & Industrial Research (DSIR), with over 5,000 license agreements concluded to date across nearly every industry sector.",
    coverage: "India — technologies from national R&D institutes across 11 sectors including agro & food processing, engineering sciences, electrical & electronics, life sciences, chemical, civil engineering, coir, glass & ceramics, herbal/personal care, sericulture, and food & millet.",
    searchHint: "Search by technology name or application area. Each result links to the full NRDC technology profile with commercialisation contact details.",
  },
  iti_sri_lanka: {
    flag: "🇱🇰",
    sizeLabel: "technology listings",
    description: "Public technology listings from Sri Lanka's Industrial Technology Institute (ITI). ITI links this catalogue as Available Technologies; current transfer availability should be confirmed directly with the institution.",
    coverage: "Sri Lanka — public ITI listings covering food, herbal-product, and environmental technologies.",
    searchHint: "Search by technology name or application area. Each result opens the original ITI technology document.",
  },
};

function sourceDetailCard(source, representedCount) {
  const detail = SOURCE_DETAIL[source.id] || {};
  const initials = sourceInitials(source.name);
  const isRedirect = source.status === "Search redirect";
  const accessLabel = isRedirect ? "External search" : "Searchable catalogue";
  const sourceId = escapeHtml(source.id);
  const sourceUrl = safeUrl(source.url);
  const capabilities = [
    !isRedirect ? "Keyword search" : "",
    source.sector_filter_supported ? "ISO sector filters" : "",
  ].filter(Boolean);
  return `
    <article class="source-detail-card" id="source-${sourceId}">
      <div class="sdc-header">
        <div class="sdc-identity">
          <span class="source-initial sdc-initial" aria-hidden="true">${escapeHtml(initials)}</span>
          <div>
            <h3 class="sdc-name">${escapeHtml(source.name)}</h3>
            <p class="sdc-institution">${escapeHtml(source.institution)}</p>
          </div>
        </div>
      </div>

      <div class="sdc-access-row">
        <span class="sdc-country">${detail.flag || ""} ${escapeHtml(source.country)}</span>
        <span class="sdc-access ${isRedirect ? "is-external" : "is-searchable"}"><i aria-hidden="true"></i>${accessLabel}</span>
      </div>

      ${Number.isFinite(representedCount) ? `<div class="sdc-catalogue-size">
        <strong>${representedCount.toLocaleString()}</strong>
        <span>records currently represented</span>
      </div>` : ""}

      <p class="sdc-description">${escapeHtml(detail.description || "")}</p>

      ${capabilities.length ? `<div class="sdc-capabilities" aria-label="Available Gateway features">
        ${capabilities.map((capability) => `<span>${capability}</span>`).join("")}
      </div>` : ""}

      <div class="sdc-actions">
        ${isRedirect && sourceUrl
          ? `<a class="button button-primary" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Search original database ↗</a>`
          : `<button class="button button-primary sdc-search-btn" data-source-search="${sourceId}">Search this source</button>`}
        <button class="button button-secondary" data-source-details="${sourceId}">Source details</button>
      </div>
    </article>
  `;
}

async function renderSourcesTable() {
  const grid = document.querySelector("#source-cards-grid");
  const badge = document.querySelector("#source-count-badge strong");
  try {
    const [sources, facets] = await withWakeupRetry(
      () => Promise.all([fetchSources(), fetchFacets().catch(() => ({ sectors: [] }))]),
      {
        onRetry: () => {
          if (grid) grid.innerHTML = `<p>Waking up the search service — this can take up to 30 seconds on first load…</p>`;
        },
      }
    );
    sourcesCache = sources;

    const countryOptions = (facets.countries || []).map((item) => ({
      value: item.value,
      label: item.label,
      count: item.count,
    }));
    const sourceOptions = (facets.sources || []).map((item) => ({
      value: item.value,
      label: item.label,
      count: item.count,
    }));
    const sectorOptions = (facets.sectors || []).map((sector) => ({
      value: sector.value,
      label: sector.label,
      count: sector.count,
    }));
    const databaseTypeOptions = DBTYPE_OPTIONS;
    sectorOptionsCache = sectorOptions;

    initMultiselect(
      els.countryMs,
      countryOptions,
      () => state.countries,
      (next) => {
        state.countries = next;
        state.mergedPage = 1;
        renderResults();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.sectorMs,
      sectorOptions,
      () => state.sectors,
      (next) => {
        state.sectors = next;
        state.mergedPage = 1;
        renderResults();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.dbtypeMs,
      databaseTypeOptions,
      () => state.databaseTypes,
      (next) => {
        state.databaseTypes = next;
        state.mergedPage = 1;
        renderResults();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.sourceMs,
      sourceOptions,
      () => state.sources,
      (next) => {
        state.sources = next;
        state.mergedPage = 1;
        renderResults();
      },
      { defaultOpen: true }
    );
    // Rank by technology/patent count, largest first — search-redirect
    // sources (e.g. WIPO) have no comparable count and are excluded from
    // the ranking, kept at the end in their original order.
    const representedCounts = new Map(
      sourceOptions
        .filter((item) => Number.isFinite(item.count))
        .map((item) => [item.value, item.count])
    );
    const rankedSources = [...sources].sort((a, b) => {
      const av = SOURCE_DETAIL[a.id]?.sizeValue;
      const bv = SOURCE_DETAIL[b.id]?.sizeValue;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return bv - av;
    });

    if (badge) badge.textContent = sources.length;
    const countryCount = new Set(countryOptions.map((country) => country.value)).size;
    const indexedCount = sources.filter((source) => source.status !== "Search redirect").length;
    const redirectCount = sources.length - indexedCount;
    const countryCountEl = document.querySelector("#source-country-count");
    const indexedCountEl = document.querySelector("#source-indexed-count");
    const redirectCountEl = document.querySelector("#source-redirect-count");
    if (countryCountEl) countryCountEl.textContent = countryCount;
    if (indexedCountEl) indexedCountEl.textContent = indexedCount;
    if (redirectCountEl) redirectCountEl.textContent = redirectCount;
    if (grid) {
      grid.innerHTML = rankedSources
        .map((source) => sourceDetailCard(source, representedCounts.get(source.id)))
        .join("");
    }
  } catch {
    if (grid) grid.innerHTML = `<p>Could not load sources.</p>`;
  }
}

// ── Event listeners ────────────────────────────────────────────────────────

function runSearch(query) {
  state.query = query.trim();
  state.mergedPage = 1;  // reset pagination on new search
  els.input.value = state.query;
  switchAppView("view-search");
  renderResults();
  document.querySelector("#search-results").scrollIntoView({ behavior: "smooth" });
}

function selectOnlySource(sourceId) {
  state.sources = [sourceId];
  els.sourceMs._render?.();
  runSearch(state.query || "");
}

window.selectOnlySource = selectOnlySource;

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  recordTrackedTopicSearch(els.input.value);
  runSearch(els.input.value);
});

document.querySelector("#popular-chips").addEventListener("click", (event) => {
  const chip = event.target.closest("[data-keyword]");
  if (chip) {
    recordTrackedTopicSearch(chip.dataset.keyword);
    runSearch(chip.dataset.keyword);
  }
});

els.clear.addEventListener("click", () => {
  state.query = "";
  state.countries = [];
  state.sectors = [];
  state.databaseTypes = [];
  state.sources = [];
  state.mergedPage = 1;
  els.input.value = "";
  syncFacetControls();
  renderResults();
});

els.activeFilters?.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-filter-type]");
  if (!chip) return;
  const { filterType, filterValue } = chip.dataset;
  if (filterType === "query") {
    state.query = "";
    els.input.value = "";
  } else if (Array.isArray(state[filterType])) {
    state[filterType] = state[filterType].filter((value) => value !== filterValue);
  }
  state.mergedPage = 1;
  syncFacetControls();
  renderResults();
});

function openFilterSheet() {
  syncFacetControls();
  els.filters.classList.add("open");
  els.filterBackdrop.hidden = false;
  requestAnimationFrame(() => els.filterBackdrop.classList.add("visible"));
}

function closeFilterSheet() {
  els.filters.classList.remove("open");
  els.filterBackdrop.classList.remove("visible");
  setTimeout(() => {
    if (!els.filters.classList.contains("open")) els.filterBackdrop.hidden = true;
  }, 200);
}

document.querySelector(".mobile-filter-button").addEventListener("click", openFilterSheet);
document.querySelector(".filter-close").addEventListener("click", closeFilterSheet);
els.filterBackdrop.addEventListener("click", closeFilterSheet);

els.resetFilters.addEventListener("click", () => {
  FILTER_STATE_KEYS.forEach((key) => {
    state[key] = [];
  });
  state.mergedPage = 1;
  multiselectInstances.forEach((container) => container._render?.());
  renderResults();
});

document.querySelector(".results-view-toggle")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-results-view]");
  if (!button) return;
  state.resultsView = button.dataset.resultsView;
  document.querySelectorAll("[data-results-view]").forEach((candidate) => {
    const active = candidate.dataset.resultsView === state.resultsView;
    candidate.classList.toggle("active", active);
    candidate.setAttribute("aria-pressed", String(active));
  });
  document.querySelector(".technology-list")?.classList.remove("view-list", "view-grid");
  document.querySelector(".technology-list")?.classList.add(`view-${state.resultsView}`);
});

// ── App view switching (Search vs Sources) ───────────────────────────────────
// The site behaves like two separate pages sharing one nav: only one
// .app-view is visible at a time. The About section lives outside both
// views and stays visible regardless — a persistent footer.

function switchAppView(viewId) {
  document.querySelectorAll(".app-view").forEach((v) => { v.hidden = v.id !== viewId; });
  const activeHref = viewId === "view-sources" ? "#sources" : "#search-results";
  document.querySelectorAll(".gateway-nav-links > a").forEach((a) => {
    a.classList.toggle("active", a.getAttribute("href") === activeHref);
  });
}

document.querySelector(".gateway-nav-brand").addEventListener("click", (e) => {
  e.preventDefault();
  switchAppView("view-search");
  document.querySelector("#gateway-home").scrollIntoView();
});

document.querySelectorAll('a[href="#search-results"]').forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    switchAppView("view-search");
    document.querySelector("#search-results").scrollIntoView();
  });
});

document.querySelector('a[href="#sources"]').addEventListener("click", (e) => {
  e.preventDefault();
  switchAppView("view-sources");
  document.querySelector("#sources").scrollIntoView();
});

// ── Source detail page (hash routing) ────────────────────────────────────────

const sourcePage = document.querySelector("#source-page");
const sourcePageContent = document.querySelector("#source-page-content");
let sourcePageReturnFocus = null;

function setSourceDialogOpen(isOpen) {
  sourcePage.classList.toggle("open", isOpen);
  sourcePage.setAttribute("aria-hidden", String(!isOpen));
  document.body.classList.toggle("source-dialog-open", isOpen);
  const main = document.querySelector("main");
  if (main) main.inert = isOpen;
}

function openSourcePage(sourceId, { pushHistory = true } = {}) {
  const source = sourcesCache.find((s) => s.id === sourceId);
  if (!source) return;
  const detail = SOURCE_DETAIL[sourceId] || {};
  const safeSourceId = escapeHtml(source.id);
  const safeSourceName = escapeHtml(source.name);
  const safeSourceUrl = safeUrl(source.url);
  const isRedirect = source.status === "Search redirect";
  sourcePageReturnFocus = document.activeElement;
  sourcePageContent.innerHTML = `
    <div class="sp-back">
      <button class="text-button" type="button" data-source-close>← Back to Gateway</button>
    </div>
    <div class="sp-hero">
      <span class="source-initial sp-initial" aria-hidden="true">${escapeHtml(sourceInitials(source.name))}</span>
      <div>
        <span class="status ${statusClass(source.status)}">${escapeHtml(source.status)}</span>
        <h2 class="sp-name" id="source-page-title">${safeSourceName}</h2>
        <p class="sp-country">${detail.flag || ""} ${escapeHtml(source.country)} · ${escapeHtml(source.institution)}</p>
      </div>
    </div>
    <p class="sp-desc">${escapeHtml(detail.description || "")}</p>
    <div class="sp-section">
      <h3>Coverage</h3>
      <p>${escapeHtml(detail.coverage || source.country)}</p>
    </div>
    ${detail.searchHint ? `<div class="sp-section sp-hint-box">
      <h3>Search tip</h3>
      <p>${escapeHtml(detail.searchHint)}</p>
    </div>` : ""}
    <div class="sp-actions">
      ${isRedirect
        ? ""
        : `<button class="button button-primary" type="button" data-source-search-and-close="${safeSourceId}">
          Search ${safeSourceName}
        </button>`}
      ${safeSourceUrl ? `<a class="button ${isRedirect ? "button-primary" : "button-secondary"}" href="${escapeHtml(safeSourceUrl)}" target="_blank" rel="noopener noreferrer">
        Visit official site ↗
      </a>` : ""}
    </div>
  `;
  setSourceDialogOpen(true);
  sourcePage.querySelector("[data-source-close]")?.focus();
  if (pushHistory) history.pushState({ sourceId }, "", `#source/${encodeURIComponent(sourceId)}`);
}

function closeSourcePage({ pushHistory = true } = {}) {
  setSourceDialogOpen(false);
  if (pushHistory) history.replaceState({}, "", "#sources");
  if (sourcePageReturnFocus instanceof HTMLElement && sourcePageReturnFocus.isConnected) {
    sourcePageReturnFocus.focus();
  }
  sourcePageReturnFocus = null;
}

window.openSourcePage = openSourcePage;
window.closeSourcePage = closeSourcePage;

window.addEventListener("popstate", (e) => {
  if (e.state?.sourceId) {
    openSourcePage(e.state.sourceId, { pushHistory: false });
  } else {
    closeSourcePage({ pushHistory: false });
  }
});

document.addEventListener("click", (event) => {
  const pageButton = event.target.closest("[data-merged-page]");
  if (pageButton) {
    changeMergedPage(Number(pageButton.dataset.mergedPage));
    return;
  }

  const searchButton = event.target.closest("[data-source-search]");
  if (searchButton) {
    selectOnlySource(searchButton.dataset.sourceSearch);
    return;
  }

  const detailsButton = event.target.closest("[data-source-details]");
  if (detailsButton) {
    openSourcePage(detailsButton.dataset.sourceDetails);
    return;
  }

  if (event.target.closest("[data-source-close]")) {
    closeSourcePage();
    return;
  }

  const dialogSearchButton = event.target.closest("[data-source-search-and-close]");
  if (dialogSearchButton) {
    const sourceId = dialogSearchButton.dataset.sourceSearchAndClose;
    closeSourcePage();
    selectOnlySource(sourceId);
  }
});

document.addEventListener("keydown", (event) => {
  const jumpInput = event.target.closest(".pagination-jump-input");
  if (jumpInput && event.key === "Enter") {
    const page = Number(jumpInput.value);
    const total = Number(jumpInput.dataset.pageTotal);
    if (Number.isInteger(page) && page >= 1 && page <= total) changeMergedPage(page);
    return;
  }

  if (!sourcePage.classList.contains("open")) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeSourcePage();
    return;
  }
  if (event.key !== "Tab") return;

  const focusable = [...sourcePage.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
  )].filter((element) => !element.hidden);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

// JPO patent status lookup JS removed pending further permission from JPO on
// the account's intended use (matching index.html and main.py). Available in
// git history — re-add along with the #jpo-lookup section once approved.

// ── Boot ─────────────────────────────────────────────────────────────────────

loadPopularSearches();

renderSourcesTable().then(() => {
  renderResults();
  // Check if URL has a source hash on load
  const match = location.hash.match(/^#source\/(.+)$/);
  if (match) openSourcePage(decodeURIComponent(match[1]), { pushHistory: false });
});
