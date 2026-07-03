const API_BASE = "https://apsei-api.onrender.com/api/v1";

// Runtime state — sources populated on init, technologies fetched on each search
let sourcesCache = [];

const GLOBAL_PAGE_SIZE = 20;

const SECTOR_OPTIONS = [
  { value: "Agriculture", label: "Agriculture & Food" },
  { value: "Energy", label: "Energy & Environment" },
  { value: "ICT", label: "Information & Communication Technology" },
  { value: "Health", label: "Health & Medical" },
  { value: "Manufacturing", label: "Manufacturing & Materials" },
  { value: "Water", label: "Water & Sanitation" },
  { value: "Transport", label: "Transport & Infrastructure" },
  { value: "Biotechnology", label: "Biotechnology" },
  { value: "Climate", label: "Climate & Disaster Risk" },
  { value: "Construction", label: "Construction & Urban Development" },
  { value: "Chemical", label: "Chemical & Pharmaceutical" },
  { value: "Electronics", label: "Electronics & Semiconductors" },
];

const DBTYPE_OPTIONS = [
  { value: "Metadata search", label: "Full technology listings" },
  { value: "Search redirect", label: "External search redirect" },
];

const state = {
  query: "",
  countries: [],
  sectors: [],
  databaseTypes: [],
  sources: [],
  transferTypes: [],
  mergedPage: 1,
};

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
  transferTypeMs: document.querySelector("#transfertype-multiselect"),
  clear: document.querySelector("#clear-filters"),
  filters: document.querySelector(".filters"),
  statsBar: document.querySelector("#global-stats-bar"),
};

// ── Multi-select filter widget ───────────────────────────────────────────────

const multiselectInstances = [];

function initMultiselect(containerEl, options, getSelected, onChange) {
  function render() {
    const selected = getSelected();
    const label = selected.length === 0
      ? containerEl.dataset.label
      : selected.length === 1
        ? (options.find((o) => o.value === selected[0])?.label || selected[0])
        : `${selected.length} selected`;

    containerEl.innerHTML = `
      <button type="button" class="multiselect-toggle">
        <span>${label}</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg>
      </button>
      <div class="multiselect-panel" hidden>
        ${options.map((o) => `
          <label class="multiselect-option">
            <input type="checkbox" value="${o.value}" ${selected.includes(o.value) ? "checked" : ""}>
            <span>${o.label}</span>
          </label>`).join("")}
      </div>`;

    containerEl.querySelector(".multiselect-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      const panel = containerEl.querySelector(".multiselect-panel");
      const willOpen = panel.hasAttribute("hidden");
      multiselectInstances.forEach((c) => c.querySelector(".multiselect-panel")?.setAttribute("hidden", ""));
      if (willOpen) panel.removeAttribute("hidden");
    });

    containerEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const next = [...containerEl.querySelectorAll('input[type="checkbox"]:checked')].map((x) => x.value);
        onChange(next);
        render();
        containerEl.querySelector(".multiselect-panel").removeAttribute("hidden");
      });
    });
  }
  render();
  containerEl._render = render;
  multiselectInstances.push(containerEl);
}

document.addEventListener("click", (e) => {
  multiselectInstances.forEach((c) => {
    if (!c.contains(e.target)) c.querySelector(".multiselect-panel")?.setAttribute("hidden", "");
  });
});

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

// ── Render functions (unchanged) ─────────────────────────────────────────────

function technologyCard(technology, source) {
  const techId = technology.id.replace("ntb_", "");
  const keywords = technology.keywords.slice(0, 6);

  const detailRows = [
    ["Organisation",      technology.org_name],
    ["Transfer type",     technology.transfer_type],
    ["Dev. status",       technology.dev_status],
    ["Sub-sector",        technology.sub_sector],
    ["Registered",        technology.reg_date],
    ["Tech ID",           techId],
  ]
    .filter(([, v]) => v)
    .map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value detail-translatable">${value}</span>
      </div>`)
    .join("");

  const needsTranslation = technology.language === "Korean";
  const flag = (SOURCE_DETAIL[source.id] || {}).flag || "";

  return `
    <article class="technology-card" data-tech-id="${technology.id}" ${needsTranslation ? 'data-needs-translation="true"' : ""}>
      <div class="card-top-row">
        <span class="card-sector">${technology.sector}</span>
        <span class="card-source-pill" title="${source.name}">${flag} ${source.name}</span>
      </div>
      <h4 class="card-title">${technology.title}</h4>
      <p class="card-summary">${technology.summary || "No summary available."}</p>
      ${keywords.length ? `
        <div class="card-keywords">
          ${keywords.map((k) => `<span class="keyword-tag">${k}</span>`).join("")}
        </div>` : ""}
      <div class="card-details">
        <span>${source.country}</span>
        <span>${technology.language}</span>
        <span>${source.name}</span>
      </div>
      <div class="card-detail-panel">
        ${detailRows}
      </div>
      <div class="card-actions">
        ${technology.url ? `<a class="button button-secondary card-external-link" href="${technology.url}" target="_blank" rel="noopener noreferrer">${technology.source_id === "ip_australia" ? "Search patent ↗" : "View on source ↗"}</a>` : ""}
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
  const content = `<div class="technology-list">
        ${info ? info.cards.map((card) => `
          <article class="technology-card external-card">
            <span class="card-sector">${card.sector}</span>
            <h4 class="card-title">${card.title}</h4>
            <p class="card-summary">${card.description}</p>
            <div class="card-details">
              <span>${card.country}</span>
              <span>${card.org}</span>
            </div>
            <div class="card-actions">
              <a class="button button-secondary card-external-link"
                 href="${buildRedirectUrl(source, state.query)}"
                 target="_blank" rel="noopener noreferrer">
                Search on ${source.name}&nbsp; →
              </a>
            </div>
          </article>`).join("") : ""}
      </div>`;

  return `
    <section class="source-group" data-source-id="${source.id}">
      <header class="group-header">
        <div class="group-source">
          <span class="source-initial" aria-hidden="true">${sourceInitials(source.name)}</span>
          <div>
            <h3>${source.name}</h3>
            <p>${source.country}</p>
          </div>
        </div>
        <div class="group-meta">
          <span class="result-count">${info ? info.size : "External source"}</span>
          <span class="status ${statusClass(source.status)}">${source.status}</span>
        </div>
      </header>
      ${content}
    </section>
  `;
}

function renderPaginationBar(current, total) {
  if (total <= 1) return "";
  const btns = [];
  const add = (p, label, active, disabled) =>
    `<button class="pagination-page-btn${active ? " active" : ""}"
      ${disabled ? "disabled" : `onclick="changeMergedPage(${p})"`}>${label}</button>`;

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
          placeholder="${current}" aria-label="Go to page"
          onkeydown="if(event.key==='Enter'){const v=parseInt(this.value);if(v>=1&&v<=${total})changeMergedPage(v);}">
        <span class="pagination-jump-label">of ${total.toLocaleString()}</span>
      </span>
    </div>`;
}

// ── Merged round-robin grid ─────────────────────────────────────────────────
// Every metadata-search source paginates independently on the backend at
// page_size=20. To show one unified, mixed grid we compute — for a given
// global page — which backend page (and local offset within it) each source
// needs, fetch those in parallel, then interleave the slices round-robin.

async function fetchSourcePage(sourceId, backendPage) {
  const data = await fetchResults({ source: sourceId, page: backendPage });
  return {
    items: (data.results || []).filter((r) => r.source_id === sourceId),
    total: data.source_totals?.[sourceId] || 0,
  };
}

async function buildMergedPage(globalPage, activeIds) {
  if (!activeIds.length) return { items: [], totalAcrossSources: 0, totalPages: 1 };

  const n = activeIds.length;
  const perSourceCount = Math.ceil(GLOBAL_PAGE_SIZE / n);
  const startOcc = (globalPage - 1) * perSourceCount;
  const endOcc = startOcc + perSourceCount; // exclusive

  const startBackendPage = Math.floor(startOcc / 20) + 1;
  const endBackendPage = Math.floor((endOcc - 1) / 20) + 1;

  const sourceMap = Object.fromEntries(sourcesCache.map((s) => [s.id, s]));
  const perSourceSlices = {};
  let totalAcrossSources = 0;

  await Promise.all(activeIds.map(async (id) => {
    const pagesNeeded = startBackendPage === endBackendPage
      ? [startBackendPage]
      : [startBackendPage, endBackendPage];
    const fetched = await Promise.all(pagesNeeded.map((p) => fetchSourcePage(id, p)));

    let combined = [];
    fetched.forEach((f, i) => {
      combined = combined.concat(f.items.map((item, idx) => ({
        item, globalOffset: (pagesNeeded[i] - 1) * 20 + idx,
      })));
    });
    const total = fetched[fetched.length - 1]?.total || fetched[0]?.total || 0;
    if (total) totalAcrossSources += total;

    const slice = combined
      .filter((c) => c.globalOffset >= startOcc && c.globalOffset < endOcc)
      .map((c) => c.item);
    perSourceSlices[id] = slice;
  }));

  const merged = [];
  for (let i = 0; i < perSourceCount; i++) {
    for (const id of activeIds) {
      const slice = perSourceSlices[id];
      if (slice && slice[i]) merged.push({ tech: slice[i], source: sourceMap[id] });
    }
  }

  const totalPages = totalAcrossSources ? Math.max(1, Math.ceil(totalAcrossSources / GLOBAL_PAGE_SIZE)) : 1;
  return { items: merged.slice(0, GLOBAL_PAGE_SIZE), totalAcrossSources, totalPages };
}

function renderMergedGrid(items) {
  if (!items.length) {
    return `<div class="empty-state"><h3>No matching technologies found</h3><p>Try a broader keyword or clear one of the filters.</p></div>`;
  }
  return `<div class="technology-list merged-grid">
    ${items.map(({ tech, source }) => technologyCard(tech, source)).join("")}
  </div>`;
}

// ── API fetch layer ───────────────────────────────────────────────────────────

async function fetchSources() {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) throw new Error("Sources fetch failed");
  return res.json();
}

async function fetchFacets() {
  const res = await fetch(`${API_BASE}/facets`);
  if (!res.ok) throw new Error("Facets fetch failed");
  return res.json();
}

// Render's free tier spins the backend down when idle — the first request
// after a while can take up to ~30-40s to wake it up, and a bare fetch
// failure would otherwise dead-end the page until the user manually retries
// (e.g. by clicking "Clear filters"). Retry silently in the background
// instead so the page self-heals on first load.
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
  if (state.transferTypes.length) params.set("transfer_type", state.transferTypes.join(","));
  if (src)            params.set("source", src);
  if (excl)           params.set("exclude", excl);
  if (page > 1)       params.set("page", page);
  const res = await fetch(`${API_BASE}/search?${params}`);
  if (!res.ok) throw new Error(`Search failed: ${res.status}`);
  return res.json();
}

// ── Rendering ─────────────────────────────────────────────────────────────────

function updateStatsBar(totalTechs, totalSources) {
  if (!els.statsBar) return;
  els.statsBar.querySelector(".gsb-number").textContent = totalTechs.toLocaleString();
  els.statsBar.querySelector(".gsb-label").textContent =
    `technolog${totalTechs === 1 ? "y" : "ies"} across ${totalSources} source platform${totalSources === 1 ? "" : "s"}. `
    + `Filter by source to view totals for each individual source.`;
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
  if (state.countries.length) ids = ids.filter((id) => state.countries.includes(sourceMap[id]?.country));
  if (state.transferTypes.length) ids = ids.filter((id) => state.transferTypes.includes(sourceMap[id]?.transfer_type));

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
    (!state.transferTypes.length || state.transferTypes.includes(s.transfer_type))
  );
}

let lastActiveIds = [];

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
        <span class="result-count">Page ${mergedPage} of ${totalPages.toLocaleString()} (${totalAcrossSources.toLocaleString()} total)</span>
        <span class="status status-metadata">Metadata search</span>
      </div>
    </header>`;
}

async function renderResults() {
  els.title.textContent = state.query ? `Results for "${state.query}"` : "Technology search results";
  els.summary.textContent = "Searching across source platforms…";
  els.results.innerHTML = `<div class="empty-state"><p>Loading results…</p></div>`;
  updateStatsBar(0, 0);

  const filterableIds = getFilterableSourceIds();
  const activeIds = getActiveMergeIds();
  const redirectSources = getRedirectSources();
  lastActiveIds = activeIds;

  let merged;
  try {
    merged = await withWakeupRetry(() => buildMergedPage(state.mergedPage, activeIds), {
      onRetry: () => {
        els.results.innerHTML = `<div class="empty-state"><p>Waking up the search service — this can take up to 30 seconds on first load…</p></div>`;
      },
    });
  } catch {
    els.results.innerHTML = `
      <div class="empty-state">
        <h3>Could not connect to the search service</h3>
        <p>The search service is temporarily unavailable. Please wait a moment and refresh.</p>
      </div>`;
    return;
  }

  const redirectHtml = redirectSources.map(redirectSourceBlock).join("");
  const gridHtml = renderMergedGrid(merged.items);
  const paginationHtml = merged.items.length ? renderPaginationBar(state.mergedPage, merged.totalPages) : "";
  const headerHtml = merged.items.length
    ? mergedGridHeader(activeIds, state.mergedPage, merged.totalPages, merged.totalAcrossSources)
    : "";

  els.results.innerHTML = `
    <div class="merged-grid-wrap">
      ${headerHtml}
      ${gridHtml}
      ${paginationHtml}
    </div>
    ${redirectHtml}`;
  autoTranslateVisibleCards();

  els.summary.textContent = merged.items.length
    ? "Explore technology offers from participating source platforms."
    : "No results on this page — try adjusting your filters.";

  const includesNTB = activeIds.includes("korea_ntb");
  updateStatsBar(merged.totalAcrossSources, filterableIds.length);

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
        updateStatsBar(merged.totalAcrossSources + ntbTotal, filterableIds.length);
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
  korea_ntb: {
    flag: "🇰🇷",
    size: "128,000+",
    sizeValue: 128000,
    sizeLabel: "technologies",
    description: "Korea's national repository for technology transfer offers from universities, research institutes, and public R&D institutions. Technologies span manufacturing, ICT, biotech, energy, and more.",
    coverage: "Republic of Korea — domestic technologies available for licensing, joint development, or transfer to domestic and international partners.",
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
    description: "Australian patent applications and grants searched via the IP Australia Patent Search API. Covers innovation patents, standard patents, and PCT national phase entries.",
    coverage: "Australia — all patent applications lodged with IP Australia, including PCT applications entering the national phase.",
    searchHint: "Results link directly to the Australian Patent Search portal for full specifications.",
  },
  csir_india: {
    flag: "🇮🇳",
    size: "1,739",
    sizeValue: 1739,
    sizeLabel: "technologies",
    description: "India's Council of Scientific and Industrial Research (CSIR) technology transfer portal — spanning 30+ national laboratories across agriculture, food, health, energy, materials, ICT, and manufacturing.",
    coverage: "India — technologies from CSIR institutes available for licensing, joint development, and commercialisation by domestic and international partners.",
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
};

function sourceDetailCard(source) {
  const detail = SOURCE_DETAIL[source.id] || {};
  const initials = sourceInitials(source.name);
  return `
    <article class="source-detail-card" id="source-${source.id}">
      <div class="sdc-header">
        <div class="sdc-identity">
          <span class="source-initial sdc-initial" aria-hidden="true">${initials}</span>
          <div>
            <h3 class="sdc-name">${source.name}</h3>
            <p class="sdc-country">${detail.flag || ""} ${source.country}</p>
          </div>
        </div>
        <span class="status ${statusClass(source.status)}">${source.status}</span>
      </div>

      ${detail.size ? `
      <div class="sdc-stat">
        <span class="sdc-stat-number">${detail.size}</span>
        <span class="sdc-stat-label">${detail.sizeLabel}</span>
      </div>` : ""}

      <p class="sdc-description">${detail.description || ""}</p>

      <div class="sdc-meta">
        <div class="sdc-meta-row">
          <span class="sdc-meta-label">Institution</span>
          <span class="sdc-meta-value">${source.institution}</span>
        </div>
        <div class="sdc-meta-row">
          <span class="sdc-meta-label">Coverage</span>
          <span class="sdc-meta-value">${detail.coverage || source.country}</span>
        </div>
        ${detail.searchHint ? `
        <div class="sdc-meta-row">
          <span class="sdc-meta-label">Search tip</span>
          <span class="sdc-meta-value sdc-hint">${detail.searchHint}</span>
        </div>` : ""}
      </div>

      <div class="sdc-actions">
        <button class="button button-primary sdc-search-btn"
          onclick="openSourcePage('${source.id}')">
          View details
        </button>
        <a class="button button-secondary" href="${source.url}" target="_blank" rel="noopener noreferrer">
          Visit source ↗
        </a>
      </div>
    </article>
  `;
}

async function renderSourcesTable() {
  const grid = document.querySelector("#source-cards-grid");
  const badge = document.querySelector("#source-count-badge strong");
  try {
    const [sources, facets] = await withWakeupRetry(
      () => Promise.all([fetchSources(), fetchFacets().catch(() => ({ transfer_types: [] }))]),
      {
        onRetry: () => {
          if (grid) grid.innerHTML = `<p>Waking up the search service — this can take up to 30 seconds on first load…</p>`;
        },
      }
    );
    sourcesCache = sources;

    // Populate filters — Transfer Type options are scraped from what each
    // registered source actually uses, not a fixed generic list.
    const countryOptions = [...new Set(sources.map((s) => s.country))].sort()
      .map((c) => ({ value: c, label: c }));
    const sourceOptions = sources.map((s) => ({ value: s.id, label: s.name }));
    const transferTypeOptions = (facets.transfer_types || []).map((t) => ({ value: t, label: t }));

    initMultiselect(els.countryMs, countryOptions, () => state.countries, (next) => {
      state.countries = next;
      state.mergedPage = 1;
      renderResults();
    });
    initMultiselect(els.sectorMs, SECTOR_OPTIONS, () => state.sectors, (next) => {
      state.sectors = next;
      state.mergedPage = 1;
      renderResults();
    });
    initMultiselect(els.dbtypeMs, DBTYPE_OPTIONS, () => state.databaseTypes, (next) => {
      state.databaseTypes = next;
      state.mergedPage = 1;
      renderResults();
    });
    initMultiselect(els.sourceMs, sourceOptions, () => state.sources, (next) => {
      state.sources = next;
      state.mergedPage = 1;
      renderResults();
    });
    initMultiselect(els.transferTypeMs, transferTypeOptions, () => state.transferTypes, (next) => {
      state.transferTypes = next;
      state.mergedPage = 1;
      renderResults();
    });

    // Rank by technology/patent count, largest first — search-redirect
    // sources (e.g. WIPO) have no comparable count and are excluded from
    // the ranking, kept at the end in their original order.
    const rankedSources = [...sources].sort((a, b) => {
      const av = SOURCE_DETAIL[a.id]?.sizeValue;
      const bv = SOURCE_DETAIL[b.id]?.sizeValue;
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return bv - av;
    });

    if (badge) badge.textContent = sources.length;
    if (grid) grid.innerHTML = rankedSources.map(sourceDetailCard).join("");
  } catch {
    if (grid) grid.innerHTML = `<p>Could not load sources.</p>`;
  }
}

// ── Event listeners ────────────────────────────────────────────────────────

function runSearch(query) {
  state.query = query.trim();
  state.mergedPage = 1;  // reset pagination on new search
  els.input.value = state.query;
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
  runSearch(els.input.value);
});

document.querySelector("#popular-chips").addEventListener("click", (event) => {
  const chip = event.target.closest("[data-keyword]");
  if (chip) runSearch(chip.dataset.keyword);
});

els.clear.addEventListener("click", () => {
  state.query = "";
  state.countries = [];
  state.sectors = [];
  state.databaseTypes = [];
  state.sources = [];
  state.transferTypes = [];
  state.mergedPage = 1;
  els.input.value = "";
  [els.countryMs, els.sectorMs, els.dbtypeMs, els.sourceMs, els.transferTypeMs].forEach((c) => c._render?.());
  renderResults();
});

document.querySelector(".mobile-filter-button").addEventListener("click", () => {
  els.filters.classList.add("open");
});

document.querySelector(".filter-close").addEventListener("click", () => {
  els.filters.classList.remove("open");
});

// ── Source detail page (hash routing) ────────────────────────────────────────

const sourcePage = document.querySelector("#source-page");
const sourcePageContent = document.querySelector("#source-page-content");

function openSourcePage(sourceId) {
  const source = sourcesCache.find((s) => s.id === sourceId);
  if (!source) return;
  const detail = SOURCE_DETAIL[sourceId] || {};
  sourcePageContent.innerHTML = `
    <div class="sp-back">
      <button class="text-button" onclick="closeSourcePage()">← Back to Gateway</button>
    </div>
    <div class="sp-hero">
      <span class="source-initial sp-initial" aria-hidden="true">${sourceInitials(source.name)}</span>
      <div>
        <span class="status ${statusClass(source.status)}">${source.status}</span>
        <h2 class="sp-name">${source.name}</h2>
        <p class="sp-country">${detail.flag || ""} ${source.country} · ${source.institution}</p>
      </div>
    </div>
    ${detail.size ? `<div class="sp-stat-row">
      <div class="sp-stat"><span class="sdc-stat-number">${detail.size}</span><span class="sdc-stat-label">${detail.sizeLabel}</span></div>
    </div>` : ""}
    <p class="sp-desc">${detail.description || ""}</p>
    <div class="sp-section">
      <h3>Coverage</h3>
      <p>${detail.coverage || source.country}</p>
    </div>
    ${detail.searchHint ? `<div class="sp-section sp-hint-box">
      <h3>Search tip</h3>
      <p>${detail.searchHint}</p>
    </div>` : ""}
    <div class="sp-actions">
      <button class="button button-primary" onclick="closeSourcePage(); selectOnlySource('${source.id}');">
        Search ${source.name}
      </button>
      <a class="button button-secondary" href="${source.url}" target="_blank" rel="noopener noreferrer">
        Visit official site ↗
      </a>
    </div>
  `;
  sourcePage.classList.add("open");
  history.pushState({ sourceId }, "", `#source/${sourceId}`);
}

function closeSourcePage() {
  sourcePage.classList.remove("open");
  history.pushState({}, "", "#sources");
}

window.openSourcePage = openSourcePage;
window.closeSourcePage = closeSourcePage;

window.addEventListener("popstate", (e) => {
  if (e.state?.sourceId) {
    openSourcePage(e.state.sourceId);
  } else {
    sourcePage.classList.remove("open");
  }
});

// ── Boot ─────────────────────────────────────────────────────────────────────

renderSourcesTable().then(() => {
  renderResults();
  // Check if URL has a source hash on load
  const match = location.hash.match(/^#source\/(.+)$/);
  if (match) openSourcePage(match[1]);
});
