const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);
const API_BASE = LOCAL_HOSTS.has(window.location.hostname)
  ? "http://127.0.0.1:8000/api/v1"
  : "https://apsei-api.onrender.com/api/v1";
const {
  escapeHtml,
  normalizeDisplayText,
  safeExternalUrl: safeUrl,
} = globalThis.AptgSecurity;
const compare = globalThis.AptgCompare;

// Runtime state — sources populated on init, technologies fetched on each search
let sourcesCache = [];
let sectorOptionsCache = [];
let activeResultsController = null;
let activeFacetController = null;
let filterRenderTimer = null;
const visibleCompareItems = new Map();

const GLOBAL_PAGE_SIZE = 20;

const DBTYPE_OPTIONS = [
  { value: "Metadata search", label: "Full technology listings" },
  { value: "Search redirect", label: "External search redirect" },
];

const FOCUS_THEME_LABELS = {
  "energy-transition": "Energy transition",
  "climate-resilient-cities": "Climate-resilient cities",
  "digital-4ir": "Digital & 4IR",
  "pollution-control": "Pollution control",
};

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
  focusTheme: "",
  resultsView: "list",
  mergedPage: 1,
  compareItems: [],
  compareTrayCollapsed: false,
};

try {
  state.compareItems = compare.readItems(window.localStorage);
} catch {
  state.compareItems = [];
}

const FILTER_STATE_KEYS = ["countries", "sectors", "databaseTypes", "sources"];

function setElementInert(element, isInert) {
  if (!element) return;
  element.toggleAttribute("inert", isInert);
  if ("inert" in element) element.inert = isInert;
}

const els = {
  form: document.querySelector("#search-form"),
  input: document.querySelector("#search-input"),
  results: document.querySelector("#results-container"),
  title: document.querySelector("#results-title"),
  summary: document.querySelector("#results-summary"),
  searchMethod: document.querySelector("#search-method-note"),
  resultsTrust: document.querySelector("#results-trust-strip"),
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
  mobileFilterButton: document.querySelector(".mobile-filter-button"),
  app: document.querySelector(".apse"),
  compareTray: document.querySelector("#compare-tray"),
  compareTrayItems: document.querySelector("#compare-tray-items"),
  compareCount: document.querySelector("#compare-count"),
  compareOpenButton: document.querySelector("#compare-open-button"),
  compareStatus: document.querySelector("#compare-status"),
  comparePage: document.querySelector("#compare-page"),
  comparePageContent: document.querySelector("#compare-page-content"),
};

const analytics = globalThis.AptgAnalytics;

function analyticsFilterCounts() {
  return {
    countries: state.countries.length,
    sectors: state.sectors.length,
    sources: state.sources.length,
    databaseTypes: state.databaseTypes.length,
  };
}

function trackSearchAnalytics(query, origin) {
  analytics?.trackSearch(query, origin, analyticsFilterCounts());
}

const analyticsFilterTypes = {
  countries: "country",
  sectors: "sector",
  sources: "source",
  databaseTypes: "database_type",
};

function trackFilterAnalytics(filterType, previous, next) {
  const analyticsType = analyticsFilterTypes[filterType] || filterType;
  const before = new Set(previous);
  const after = new Set(next);
  next.filter((value) => !before.has(value)).forEach((value) => {
    analytics?.trackFilter(analyticsType, "add", value, next.length);
  });
  previous.filter((value) => !after.has(value)).forEach((value) => {
    analytics?.trackFilter(analyticsType, "remove", value, next.length);
  });
}

// ── Facet filter groups ──────────────────────────────────────────────────────

const multiselectInstances = [];

function initMultiselect(containerEl, options, getSelected, onChange, {
  defaultOpen = false,
  previewLimit = 5,
  searchable = true,
} = {}) {
  let isOpen = defaultOpen;
  let showAll = false;
  let searchTerm = "";
  const groupLabel = containerEl.previousElementSibling?.textContent?.trim() || "Filter";

  function render({ focusSearch = false } = {}) {
    const selected = getSelected();
    const selectedSet = new Set(selected);
    const normalizedSearch = searchTerm.trim().toLowerCase();
    const rankedOptions = [...options].sort((a, b) => {
      const selectedDifference = Number(selectedSet.has(b.value)) - Number(selectedSet.has(a.value));
      if (selectedDifference) return selectedDifference;
      const aCount = Number.isFinite(a.count) ? a.count : -1;
      const bCount = Number.isFinite(b.count) ? b.count : -1;
      return bCount - aCount || a.label.localeCompare(b.label);
    });
    const filteredOptions = normalizedSearch
      ? rankedOptions.filter((option) => `${option.label} ${option.value}`.toLowerCase().includes(normalizedSearch))
      : rankedOptions;
    const visibleOptions = showAll || normalizedSearch || filteredOptions.length <= previewLimit
      ? filteredOptions
      : filteredOptions.slice(0, previewLimit);
    const canSearch = searchable && options.length > 8;
    const hasMore = filteredOptions.length > previewLimit;

    containerEl.innerHTML = `
      <button type="button" class="facet-group-toggle" aria-expanded="${isOpen}">
        <span>${escapeHtml(groupLabel)}${selected.length ? ` <strong>${selected.length}</strong>` : ""}</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 8 5 5 5-5" /></svg>
      </button>
      <div class="facet-options" ${isOpen ? "" : "hidden"}>
        ${canSearch ? `<label class="facet-search">
          <span class="visually-hidden">Search ${escapeHtml(groupLabel.toLowerCase())}</span>
          <input type="search" value="${escapeHtml(searchTerm)}" placeholder="Search ${escapeHtml(groupLabel.toLowerCase())}" autocomplete="off">
        </label>` : ""}
        <div class="facet-option-list">
          ${visibleOptions.map((o) => `
            <label class="facet-option">
              <span>
                <input type="checkbox" value="${escapeHtml(o.value)}" ${selectedSet.has(o.value) ? "checked" : ""}>
                <span>${escapeHtml(o.label)}</span>
              </span>
              ${Number.isFinite(o.count)
                ? `<small>${o.count.toLocaleString()}</small>`
                : `<small class="facet-availability" aria-label="Available. This source is connected, but its results cannot be counted in advance." title="Source available — count not available in advance."><span aria-hidden="true"></span></small>`}
            </label>`).join("") || `<p class="facet-no-options">No matching filters</p>`}
        </div>
        ${hasMore && !normalizedSearch ? `<button type="button" class="facet-list-toggle" aria-expanded="${showAll}">
          ${showAll ? "Show fewer" : `Show all ${filteredOptions.length}`}
        </button>` : ""}
      </div>`;

    containerEl.querySelector(".facet-group-toggle").addEventListener("click", () => {
      isOpen = !isOpen;
      render();
    });

    const searchInput = containerEl.querySelector('.facet-search input');
    searchInput?.addEventListener("input", () => {
      searchTerm = searchInput.value;
      render({ focusSearch: true });
    });

    containerEl.querySelector(".facet-list-toggle")?.addEventListener("click", () => {
      showAll = !showAll;
      render();
    });

    containerEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const next = new Set(getSelected());
        if (cb.checked) next.add(cb.value);
        else next.delete(cb.value);
        onChange([...next]);
        render();
      });
    });

    if (focusSearch) {
      const nextInput = containerEl.querySelector('.facet-search input');
      nextInput?.focus();
      nextInput?.setSelectionRange(nextInput.value.length, nextInput.value.length);
    }
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

function cancelScheduledFilterRender() {
  if (filterRenderTimer) clearTimeout(filterRenderTimer);
  filterRenderTimer = null;
}

function scheduleFilterRender() {
  cancelScheduledFilterRender();
  filterRenderTimer = setTimeout(() => {
    filterRenderTimer = null;
    renderResults();
  }, 180);
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

function formatIndexedDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || "")) return "";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

function formatSourceDate(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "";
  if (/^\d{8}$/.test(normalized)) {
    return formatIndexedDate(
      `${normalized.slice(0, 4)}-${normalized.slice(4, 6)}-${normalized.slice(6, 8)}`
    );
  }
  return formatIndexedDate(normalized) || normalized;
}

function readinessDisplay(value) {
  const sourceValue = String(value || "").trim();
  const plainStatuses = {
    transfer: "Available for transfer",
    prototype: "Prototype stage",
    experimental: "Experimental stage",
    initial: "Initial development",
  };
  if (plainStatuses[sourceValue.toLowerCase()]) {
    return plainStatuses[sourceValue.toLowerCase()];
  }
  const trl = sourceValue.match(/\bTRL\s*[-–—:]?\s*([1-9])\b/i);
  if (!trl) return sourceValue;
  const level = Number(trl[1]);
  const stage = level <= 3
    ? "Early-stage research"
    : level <= 6
      ? "Development and validation"
      : level <= 8
        ? "Demonstration stage"
        : "Proven in operation";
  return `${stage} · TRL ${level}`;
}

function languageName(value) {
  const key = String(value || "").trim().toLowerCase();
  return {
    en: "English",
    english: "English",
    ko: "Korean",
    korean: "Korean",
    th: "Thai",
    thai: "Thai",
    ms: "Malay",
    malay: "Malay",
  }[key] || String(value || "").trim();
}

function translationDisplay(technology) {
  const status = String(technology.translation_status || "").toLowerCase();
  const language = languageName(technology.language);
  if (status.startsWith("translated")) {
    return `Machine-translated from ${language || "the source language"}`;
  }
  if (language && language !== "English" && technology.source_id === "korea_ntb") {
    return `Original ${language}`;
  }
  return "";
}

function flagForCountry(country, source) {
  if (country === source.country) return (SOURCE_DETAIL[source.id] || {}).flag || "";
  const matchingSource = sourcesCache.find((candidate) =>
    candidate.country === country && (SOURCE_DETAIL[candidate.id] || {}).flag
  );
  return matchingSource ? SOURCE_DETAIL[matchingSource.id].flag : "";
}

const JST_PATENT_LIST_URL = "https://www.jst.go.jp/chizai/en/patent_en.html";
const JST_LICENSING_EMAIL = "license@jst.go.jp";

function jstPatentLinks(technology) {
  if (technology.source_id !== "jst_japan") return null;

  const referenceId = String(technology.reference_id || "").trim();
  const hasPatentDocument = /^\d+$/.test(referenceId);
  const officialUrl = JST_PATENT_LIST_URL;
  const destinationUrl = hasPatentDocument
    ? `https://www.jst.go.jp/chizai/pdf/US${referenceId}B2.pdf`
    : `https://patents.google.com/?q=${encodeURIComponent(`"${referenceId}" "${technology.title}"`)}`;
  const referenceLabel = hasPatentDocument ? "US patent number" : "US application number";
  const referenceDisplay = referenceId
    ? `${hasPatentDocument ? "US " : ""}${referenceId}`
    : "See JST patent listing";
  const subjectReference = referenceId
    ? `${hasPatentDocument ? "US Patent" : "US Patent Application"} ${referenceId}`
    : technology.title;
  const subject = `Licensing inquiry – ${subjectReference}`;
  const body = [
    "Dear JST Department of Intellectual Property Management,",
    "",
    "I am interested in the following invention listed by JST:",
    `Title: ${technology.title}`,
    referenceId ? `${referenceLabel}: ${referenceDisplay}` : null,
    `Official JST listing: ${officialUrl}`,
    "",
    "Organisation:",
    "Intended use:",
    "Country/region:",
    "",
    "Kind regards,",
  ].filter((line) => line !== null).join("\n");

  return {
    destinationUrl,
    destinationLabel: hasPatentDocument ? "Open JST patent document ↗" : "Find on Google Patents ↗",
    officialUrl,
    hasPatentDocument,
    referenceLabel,
    referenceDisplay,
    inquiryUrl: `mailto:${JST_LICENSING_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`,
  };
}

// ── Render functions ──────────────────────────────────────────────────────────

// Technology fields come from crawled external sources, not from us — never
// trust them into innerHTML unescaped (a scraped title/summary containing
// "<img onerror=...>" would otherwise execute in every visitor's browser).
function compareItemForTechnology(technology, source, {
  sectorText = "",
  destinationUrl = "",
  destinationLabel = "",
  summary = "",
} = {}) {
  return compare.normalizeItem({
    id: technology.id,
    sourceId: source.id,
    sourceName: source.name,
    title: technology.title,
    summary: summary || technology.summary,
    country: technology.country || source.country,
    sectors: sectorText || (technology.sector_labels || []).join(", ") || technology.sector,
    organisation: technology.org_name,
    recordDate: technology.reg_date,
    lastIndexed: formatIndexedDate(source.last_indexed),
    language: technology.language,
    url: destinationUrl || technology.url,
    linkLabel: destinationLabel || "Open source record ↗",
  });
}

function technologyCard(technology, source) {
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
  const inventorOnlySummary = technology.source_id === "jst_japan"
    && /^Inventors?:/i.test(technology.summary || "");
  const cardSummary = inventorOnlySummary
    ? "Patent available for international licensing through JST."
    : technology.summary;

  const jstLinks = jstPatentLinks(technology);
  const provider = String(technology.org_name || source.institution || "").trim();
  const readiness = readinessDisplay(technology.dev_status);
  const sourceDate = formatSourceDate(technology.reg_date);
  const indexedDate = formatIndexedDate(source.last_indexed);
  const currency = indexedDate ? `Indexed ${indexedDate}` : "Live source";
  const translationNote = translationDisplay(technology);
  const needsTranslation = technology.language === "Korean";
  const fact = (label, value, sourceValue = "", translatable = false) => value ? `
    <div class="card-fact">
      <span class="card-fact-label">${label}</span>
      <strong class="card-fact-value${translatable ? " detail-translatable" : ""}"${sourceValue ? ` title="Source value: ${escapeHtml(sourceValue)}"` : ""}>${escapeHtml(value)}</strong>
    </div>` : "";
  const detailRows = [
    ["Standardized sectors", sectorLabels.length > 1 ? allSectors : ""],
    ...(jstLinks ? [[jstLinks.referenceLabel, jstLinks.referenceDisplay]] : []),
  ]
    .filter(([, v]) => v)
    .map(([label, value]) => `
      <div class="detail-row">
        <span class="detail-label">${label}</span>
        <span class="detail-value detail-translatable">${escapeHtml(value)}</span>
      </div>`)
    .join("");

  const cardCountry = technology.country || source.country;
  const flag = flagForCountry(cardCountry, source);
  const url = safeUrl(jstLinks?.destinationUrl || technology.url);
  const compareItem = compareItemForTechnology(technology, source, {
    sectorText: allSectors || sectorLabel || technology.sector,
    destinationUrl: url,
    destinationLabel: jstLinks?.destinationLabel || "Open source record ↗",
    summary: cardSummary,
  });
  const compareKey = compare.itemKey(compareItem);
  const isCompared = state.compareItems.some((item) => compare.itemKey(item) === compareKey);
  if (compareItem && compareKey) visibleCompareItems.set(compareKey, compareItem);
  const jstContactDetails = jstLinks ? `
    <div class="jst-contact-details">
      <div class="detail-row">
        <span class="detail-label">Licensing contact</span>
        <a class="detail-value" href="mailto:${JST_LICENSING_EMAIL}">${JST_LICENSING_EMAIL}</a>
      </div>
      <div class="detail-row">
        <span class="detail-label">Official source</span>
        <a class="detail-value" href="${escapeHtml(jstLinks.officialUrl)}" target="_blank" rel="noopener noreferrer">View official JST listing ↗</a>
      </div>
      <p>Send licensing enquiries to JST. Please do not contact individual inventors directly.</p>
      ${jstLinks.hasPatentDocument ? "" : "<p>Google Patents is provided as an external discovery aid. Confirm current status and licensing availability with JST.</p>"}
    </div>` : "";

  return `
    <article class="technology-card" data-tech-id="${escapeHtml(technology.id)}" data-source-id="${escapeHtml(source.id)}" ${needsTranslation ? 'data-needs-translation="true"' : ""}>
      <div class="card-top-row">
        <div class="card-context">
          <span class="card-sector">${sectorDisplay}</span>
          <span class="card-country">${flag} ${escapeHtml(cardCountry)}</span>
        </div>
        <span class="card-source-pill" title="${escapeHtml(source.name)}">${escapeHtml(source.name)}</span>
      </div>
      <h4 class="card-title">${escapeHtml(technology.title)}</h4>
      <p class="card-summary">${escapeHtml(cardSummary) || "Description available from the original source."}</p>
      <div class="card-facts" aria-label="Key source information">
        ${fact("Provider", provider, "", needsTranslation)}
        ${fact("Readiness", readiness, technology.dev_status, needsTranslation)}
        ${fact("Source date", sourceDate)}
        ${fact("Data currency", currency)}
      </div>
      ${translationNote ? `<p class="card-translation-note">${escapeHtml(translationNote)}</p>` : ""}
      <div class="card-footer">
        ${detailRows ? `
          <details class="card-detail-disclosure">
            <summary>Additional source details</summary>
            <div class="card-detail-panel">${detailRows}${jstContactDetails}</div>
          </details>` : "<span></span>"}
        <div class="card-actions">
          ${compareKey ? `<button class="button button-secondary compare-toggle${isCompared ? " is-selected" : ""}" type="button" data-compare-toggle="${escapeHtml(compareKey)}" aria-pressed="${String(isCompared)}">
            <span aria-hidden="true">${isCompared ? "✓" : "+"}</span> ${isCompared ? "Added to compare" : "Add to compare"}
          </button>` : ""}
          ${jstLinks ? `<a class="button button-secondary card-contact-link" data-analytics-outbound="licensing_inquiry" data-analytics-source="jst_japan" href="${escapeHtml(jstLinks.inquiryUrl)}">Contact JST about licensing</a>` : ""}
          ${url ? `<a class="button button-primary card-external-link" data-analytics-outbound="technology_record" data-analytics-source="${escapeHtml(source.id)}" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${jstLinks ? jstLinks.destinationLabel : "Open source record ↗"}</a>` : ""}
        </div>
      </div>
    </article>
  `;
}

// Google's public translate endpoint is used only for Korean NTB metadata —
// no API key needed. Long text gets split into multiple chunks in the
// response, which we rejoin.
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
    const translationNote = card.querySelector(".card-translation-note");
    if (translationNote) translationNote.textContent = "Machine-translated from Korean";
    card.classList.add("translated");
  } catch {
    const translationNote = card.querySelector(".card-translation-note");
    if (translationNote) translationNote.textContent = "Original Korean · translation unavailable";
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
                   data-analytics-outbound="external_search"
                   data-analytics-source="${sourceId}"
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
    focusTheme: state.focusTheme,
  });
}

async function fetchSourcePage(sourceId, backendPage, signal) {
  const key = sourcePageCacheKey(sourceId, backendPage);
  if (sourcePageCache.has(key)) return sourcePageCache.get(key);

  const request = fetchResults({ source: sourceId, page: backendPage }, signal)
    .then((data) => {
      const result = {
        items: (data.results || []).filter((r) => r.source_id === sourceId),
        total: data.source_totals?.[sourceId] || 0,
        failed: (data.failed_sources || []).includes(sourceId),
        searchMode: data.search_mode || "keyword",
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

async function buildMergedPage(globalPage, activeIds, signal) {
  if (!activeIds.length) {
    return {
      items: [],
      page: 1,
      totalAcrossSources: 0,
      totalPages: 1,
      failedSources: [],
      searchMode: "keyword",
    };
  }

  const sourceMap = Object.fromEntries(sourcesCache.map((s) => [s.id, s]));
  const firstPages = await Promise.all(activeIds.map((id) => fetchSourcePage(id, 1, signal)));
  const sourceTotals = Object.fromEntries(
    activeIds.map((id, index) => [id, firstPages[index].total])
  );
  const failedSources = new Set(
    activeIds.filter((id, index) => firstPages[index].failed)
  );
  const searchModes = firstPages.map((page) => page.searchMode);
  const searchMode = searchModes.includes("semantic")
    ? "semantic"
    : searchModes.includes("expanded") ? "expanded" : "keyword";

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
    const data = await fetchSourcePage(sourceId, backendPage, signal);
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
    searchMode,
  };
}

function renderMergedGrid(items, searchMode = "keyword") {
  visibleCompareItems.clear();
  if (!items.length) {
    if (state.query && searchMode === "semantic") {
      return `<div class="empty-state search-empty-state">
        <h3>No strong matches for “${escapeHtml(state.query)}”</h3>
        <p>We did not find a strong connection to the indexed titles or descriptions, so weak suggestions were hidden.</p>
        <div class="empty-state-actions">
          <button class="button button-secondary" type="button" data-clear-query>Clear search</button>
          <a class="text-button" href="#sources">Browse source platforms</a>
        </div>
      </div>`;
    }
    const heading = state.query
      ? `No technologies available for “${escapeHtml(state.query)}”`
      : "No matching technologies found";
    return `<div class="empty-state search-empty-state"><h3>${heading}</h3><p>Try a broader keyword or clear one of the filters.</p></div>`;
  }
  return `<div class="technology-list merged-grid view-${state.resultsView}">
    ${items.map(({ tech, source }) => technologyCard(tech, source)).join("")}
  </div>`;
}

// ── Client-side technology comparison ───────────────────────────────────────

let comparePageReturnFocus = null;

function announceCompare(message) {
  if (!els.compareStatus) return;
  els.compareStatus.textContent = "";
  requestAnimationFrame(() => { els.compareStatus.textContent = message; });
}

function saveCompareItems(items) {
  try {
    state.compareItems = compare.writeItems(window.localStorage, items);
  } catch {
    state.compareItems = compare.normalizeItems(items);
  }
}

function updateCompareButtons() {
  const selectedKeys = new Set(state.compareItems.map(compare.itemKey));
  document.querySelectorAll("[data-compare-toggle]").forEach((button) => {
    const selected = selectedKeys.has(button.dataset.compareToggle);
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.innerHTML = `<span aria-hidden="true">${selected ? "✓" : "+"}</span> ${selected ? "Added to compare" : "Add to compare"}`;
  });
}

function renderCompareTray() {
  const count = state.compareItems.length;
  els.compareTray.hidden = count === 0;
  document.body.classList.toggle("has-compare-tray", count > 0);
  document.body.classList.toggle("compare-tray-collapsed", count > 0 && state.compareTrayCollapsed);
  els.compareTray.classList.toggle("is-collapsed", state.compareTrayCollapsed);
  els.compareCount.textContent = `${count} of ${compare.LIMIT} selected`;
  els.compareOpenButton.disabled = count < 2;
  els.compareOpenButton.textContent = count < 2 ? "Select one more" : `Compare ${count} technologies`;
  els.compareTrayItems.innerHTML = state.compareItems.map((item) => {
    const key = compare.itemKey(item);
    return `
      <span class="compare-tray-item" title="${escapeHtml(item.title)}">
        <span>${escapeHtml(item.title)}</span>
        <button type="button" data-compare-remove="${escapeHtml(key)}" aria-label="Remove ${escapeHtml(item.title)} from comparison">×</button>
      </span>`;
  }).join("");
  const trayToggle = els.compareTray.querySelector("[data-compare-tray-toggle]");
  if (trayToggle) {
    trayToggle.setAttribute("aria-expanded", String(!state.compareTrayCollapsed));
    trayToggle.textContent = state.compareTrayCollapsed ? "Show selections" : "Hide selections";
  }
  updateCompareButtons();
}

function missingCompareValue() {
  return '<span class="compare-missing">Not provided by source</span>';
}

function compareTextCell(item, field) {
  return item[field] ? escapeHtml(item[field]) : missingCompareValue();
}

function renderComparePage() {
  const items = state.compareItems;
  if (items.length < 2) {
    els.comparePageContent.innerHTML = `
      <div class="compare-page-empty">
        <h1 id="compare-page-title">Choose at least two technologies</h1>
        <p>Add another technology from the search results to compare the available metadata side by side.</p>
        <button class="button button-primary" type="button" data-compare-close>Return to search results</button>
      </div>`;
    return;
  }

  const headers = items.map((item) => `
    <th scope="col">
      <span class="compare-source-name">${escapeHtml(item.sourceName)}</span>
      <h2>${escapeHtml(item.title)}</h2>
      <button class="text-button compare-column-remove" type="button" data-compare-remove="${escapeHtml(compare.itemKey(item))}">Remove</button>
    </th>`).join("");

  const textRow = (label, field, rowClass = "") => `
    <tr${rowClass ? ` class="${rowClass}"` : ""}>
      <th scope="row">${label}</th>
      ${items.map((item) => `<td>${compareTextCell(item, field)}</td>`).join("")}
    </tr>`;

  const sourceLinks = items.map((item) => `<td>${item.url
    ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" data-analytics-outbound="technology_record" data-analytics-source="${escapeHtml(item.sourceId)}">${escapeHtml(item.linkLabel || "View original source ↗")}</a>`
    : missingCompareValue()}</td>`).join("");

  const mobileValues = (field, { links = false } = {}) => items.map((item) => `
    <div class="compare-mobile-value">
      <div class="compare-mobile-technology">
        <span>${escapeHtml(item.sourceName)}</span>
        <h3>${escapeHtml(item.title)}</h3>
      </div>
      <div>${links
        ? item.url
          ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer" data-analytics-outbound="technology_record" data-analytics-source="${escapeHtml(item.sourceId)}">${escapeHtml(item.linkLabel || "View original source ↗")}</a>`
          : missingCompareValue()
        : compareTextCell(item, field)}</div>
    </div>`).join("");

  const mobileField = (label, field, { collapsible = false, links = false } = {}) => collapsible
    ? `<details class="compare-mobile-field compare-mobile-field-collapsible">
        <summary>${label}<span>Show summaries</span></summary>
        <div class="compare-mobile-values">${mobileValues(field, { links })}</div>
      </details>`
    : `<section class="compare-mobile-field">
        <h2>${label}</h2>
        <div class="compare-mobile-values">${mobileValues(field, { links })}</div>
      </section>`;

  els.comparePageContent.innerHTML = `
    <header class="compare-page-heading">
      <h1 id="compare-page-title">Compare selected technologies</h1>
      <p>${items.length} technologies selected. Missing information means the source did not provide that field.</p>
    </header>
    <p class="compare-scroll-hint">Swipe horizontally to view every selected technology.</p>
    <div class="compare-table-wrap" tabindex="0" aria-label="Scrollable technology comparison table">
      <table class="compare-table">
        <caption class="visually-hidden">Comparison of ${items.length} selected technologies</caption>
        <thead>
          <tr>
            <th scope="col"><span class="visually-hidden">Comparison field</span></th>
            ${headers}
          </tr>
        </thead>
        <tbody>
          ${textRow("Summary", "summary", "compare-summary-row")}
          ${textRow("Country", "country")}
          ${textRow("Standardized sector", "sectors")}
          ${textRow("Organisation", "organisation")}
          ${textRow("Source record date", "recordDate")}
          ${textRow("Last indexed by APTG", "lastIndexed")}
          ${textRow("Source platform", "sourceName")}
          <tr class="compare-link-row">
            <th scope="row">Full record</th>
            ${sourceLinks}
          </tr>
        </tbody>
      </table>
    </div>
    <div class="compare-mobile-fields" aria-label="Technology comparison by field">
      ${mobileField("Summary", "summary", { collapsible: true })}
      ${mobileField("Country", "country")}
      ${mobileField("Standardized sector", "sectors")}
      ${mobileField("Organisation", "organisation")}
      ${mobileField("Source record date", "recordDate")}
      ${mobileField("Last indexed by APTG", "lastIndexed")}
      ${mobileField("Source platform", "sourceName")}
      ${mobileField("Full record", "url", { links: true })}
    </div>
    <p class="compare-authority-note">Original source platforms remain authoritative. Verify current details and availability before making decisions.</p>`;
}

function setComparePageOpen(isOpen) {
  els.comparePage.classList.toggle("open", isOpen);
  els.comparePage.setAttribute("aria-hidden", String(!isOpen));
  document.body.classList.toggle("compare-dialog-open", isOpen);
  const main = document.querySelector("main");
  setElementInert(main, isOpen);
  setElementInert(els.compareTray, isOpen);
}

function openComparePage() {
  if (state.compareItems.length < 2) {
    announceCompare("Select at least two technologies to compare.");
    return;
  }
  comparePageReturnFocus = document.activeElement;
  renderComparePage();
  setComparePageOpen(true);
  els.comparePage.querySelector("[data-compare-close]")?.focus();
}

function closeComparePage() {
  setComparePageOpen(false);
  if (comparePageReturnFocus instanceof HTMLElement && comparePageReturnFocus.isConnected) {
    comparePageReturnFocus.focus();
  }
  comparePageReturnFocus = null;
}

function removeComparedItem(key) {
  const removed = state.compareItems.find((item) => compare.itemKey(item) === key);
  if (!removed) return;
  saveCompareItems(state.compareItems.filter((item) => compare.itemKey(item) !== key));
  renderCompareTray();
  if (els.comparePage.classList.contains("open")) renderComparePage();
  announceCompare(`${removed.title} removed from comparison.`);
}

async function translateComparedItem(key) {
  const index = state.compareItems.findIndex((item) => compare.itemKey(item) === key);
  const item = state.compareItems[index];
  if (!item || item.language !== "Korean") return;
  const fields = ["title", "summary", "sectors", "organisation"];
  try {
    const translated = await Promise.all(fields.map((field) => translateText(item[field])));
    if (state.compareItems[index] !== item) return;
    const nextItem = { ...item, language: "English" };
    fields.forEach((field, fieldIndex) => { nextItem[field] = translated[fieldIndex] || item[field]; });
    saveCompareItems(state.compareItems.map((candidate, candidateIndex) => candidateIndex === index ? nextItem : candidate));
    renderCompareTray();
    if (els.comparePage.classList.contains("open")) renderComparePage();
  } catch {
    // Keep the original source language when automatic translation is unavailable.
  }
}

function toggleComparedItem(key) {
  const visibleItem = visibleCompareItems.get(key);
  const existingItem = state.compareItems.find((item) => compare.itemKey(item) === key);
  const result = compare.toggleItem(state.compareItems, visibleItem || existingItem);
  if (result.status === "limit") {
    announceCompare(`You can compare up to ${compare.LIMIT} technologies. Remove one before adding another.`);
    return;
  }
  if (result.status === "invalid") return;
  saveCompareItems(result.items);
  renderCompareTray();
  const item = visibleItem || existingItem;
  announceCompare(result.status === "added"
    ? `${item.title} added to comparison. ${state.compareItems.length} of ${compare.LIMIT} selected.`
    : `${item.title} removed from comparison.`);
  if (result.status === "added") translateComparedItem(key);
}

// ── API fetch layer ───────────────────────────────────────────────────────────

async function fetchSources() {
  const res = await fetch(`${API_BASE}/sources`);
  if (!res.ok) throw new Error("Sources fetch failed");
  return res.json();
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

async function fetchFacets({ signal } = {}) {
  const params = new URLSearchParams();
  if (state.query) params.set("q", state.query);
  if (state.countries.length) params.set("country", state.countries.join(","));
  if (state.sectors.length) params.set("sector", state.sectors.join(","));
  if (state.sources.length) params.set("source", state.sources.join(","));
  if (state.databaseTypes.length) params.set("database_type", state.databaseTypes.join(","));
  if (state.focusTheme) params.set("focus", state.focusTheme);
  const res = await fetch(`${API_BASE}/facets?${params}`, { signal });
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
  activeFacetController?.abort();
  const controller = new AbortController();
  activeFacetController = controller;
  let facets;
  try {
    facets = await fetchFacets({ signal: controller.signal });
  } catch (error) {
    if (error.name === "AbortError") return;
    throw error;
  } finally {
    if (activeFacetController === controller) activeFacetController = null;
  }
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
      if (e?.name === "AbortError") throw e;
      lastErr = e;
      if (i < attempts - 1) {
        onRetry?.(i + 1, attempts);
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }
  }
  throw lastErr;
}

async function fetchResults(overrides = {}, signal) {
  const params = new URLSearchParams();
  const page = overrides.page || 1;
  const src  = overrides.source !== undefined ? overrides.source : state.sources.join(",");
  const excl = overrides.exclude;
  if (state.query)          params.set("q", state.query);
  if (state.countries.length) params.set("country", state.countries.join(","));
  if (state.sectors.length)   params.set("sector", state.sectors.join(","));
  if (state.focusTheme)       params.set("focus", state.focusTheme);
  if (src)            params.set("source", src);
  if (excl)           params.set("exclude", excl);
  if (page > 1)       params.set("page", page);
  const res = await fetch(`${API_BASE}/search?${params}`, { signal });
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
    state.focusTheme ||
    state.countries.length ||
    state.sectors.length ||
    state.databaseTypes.length ||
    state.sources.length
  );
}

function syncSearchMode() {
  els.app?.classList.toggle("has-active-search", hasActiveSearch());
  const activeFilterCount = FILTER_STATE_KEYS.reduce((total, key) => total + state[key].length, 0)
    + (state.focusTheme ? 1 : 0);
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
    ...(state.focusTheme ? [{
      type: "focusTheme",
      value: state.focusTheme,
      label: `Featured theme: ${FOCUS_THEME_LABELS[state.focusTheme] || state.focusTheme}`,
    }] : []),
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

function syncFocusThemeChips() {
  const container = document.querySelector("#focus-theme-chips");
  const note = document.querySelector("#focus-theme-note");
  if (!container) return;
  container.querySelectorAll("[data-focus]").forEach((button) => {
    const active = button.dataset.focus === state.focusTheme;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  if (note) {
    note.textContent = state.focusTheme
      ? "Curated results based on related sectors and technology terms. Clear the theme to search every catalogue."
      : "Choose a theme or continue searching across all technology areas.";
  }
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
      const nextSources = state.sources.includes(id) ? [] : [id];
      trackFilterAnalytics("source", state.sources, nextSources);
      state.sources = nextSources;
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
  if (state.focusTheme) ids = ids.filter((id) => sourceMap[id]?.focus_filter_supported);

  return ids;
}

function getActiveMergeIds() {
  let ids = getFilterableSourceIds();

  // Korea NTB's external API takes up to 25s — excluded from the round-robin
  // pool unless explicitly requested, so it doesn't stall every page load.
  const explicitlyWantsNTB = state.sources.includes("korea_ntb") || state.countries.includes("Republic of Korea");
  if (!explicitlyWantsNTB) ids = ids.filter((id) => id !== "korea_ntb");

  return ids;
}

function getRedirectSources() {
  if (state.databaseTypes.length && !state.databaseTypes.includes("Search redirect")) return [];
  return sourcesCache.filter((s) =>
    s.status === "Search redirect" &&
    (!state.sources.length || state.sources.includes(s.id)) &&
    (!state.countries.length || state.countries.includes(s.country)) &&
    !state.sectors.length &&
    !state.focusTheme
  );
}

let lastActiveIds = [];
let renderResultsToken = 0;

function updateSearchMethodNote(searchMode, total) {
  if (!els.searchMethod) return;
  if (!state.query) {
    els.searchMethod.hidden = true;
    els.searchMethod.textContent = "";
    return;
  }

  els.searchMethod.hidden = false;
  if (searchMode === "semantic") {
    els.searchMethod.textContent = total
      ? "Results may include closely related concepts, not only exact words. Weak matches are hidden."
      : "No strong matches were found. Weak suggestions were hidden rather than presented as results.";
  } else if (searchMode === "expanded") {
    els.searchMethod.textContent = "Results may include related technical terms, not only the exact words entered.";
  } else {
    els.searchMethod.textContent = "Results currently match the words entered. Related-concept search is temporarily unavailable.";
  }
}

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
  activeResultsController?.abort();
  sourcePageCache.clear();
  const requestController = new AbortController();
  activeResultsController = requestController;
  syncSearchMode();
  syncFocusThemeChips();
  renderActiveFilters();
  refreshFacetCounts(token).catch(() => {});

  const focusLabel = FOCUS_THEME_LABELS[state.focusTheme];
  els.title.textContent = state.query
    ? `Results for "${state.query}"`
    : focusLabel || "Technology search results";
  els.summary.textContent = "Searching across source platforms…";
  updateSearchMethodNote("keyword", 0);
  if (els.searchMethod) els.searchMethod.hidden = true;
  els.results.innerHTML = `<div class="empty-state"><p>Loading results…</p></div>`;
  if (els.resultsTrust) els.resultsTrust.hidden = true;
  updateStatsBar(0, 0, 0);
  renderSourceChips();

  const filterableIds = getFilterableSourceIds();
  const activeIds = getActiveMergeIds();
  const redirectSources = getRedirectSources();
  lastActiveIds = activeIds;

  let merged;
  try {
    merged = await withWakeupRetry(() => buildMergedPage(state.mergedPage, activeIds, requestController.signal), {
      onRetry: () => {
        if (token === renderResultsToken) {
          els.results.innerHTML = `<div class="empty-state"><p>Waking up the search service — this can take up to 30 seconds on first load…</p></div>`;
        }
      },
    });
  } catch (error) {
    if (activeResultsController === requestController) activeResultsController = null;
    if (error.name === "AbortError") return;
    if (token === renderResultsToken) {
      els.results.innerHTML = `
        <div class="empty-state">
          <h3>Could not connect to the search service</h3>
          <p>The search service is temporarily unavailable. Please wait a moment and refresh.</p>
        </div>`;
    }
    return;
  }

  if (activeResultsController === requestController) activeResultsController = null;

  if (token !== renderResultsToken) return; // a newer call already started; discard this stale result
  state.mergedPage = merged.page;
  // The search request may have created and cached a semantic query vector.
  // Refresh once more so facet counts follow the same expanded result set.
  refreshFacetCounts(token).catch(() => {});

  // Blank state — no search term and no filters applied. Show only the
  // indexed source information (name, coverage, counts) rather than
  // flooding the page with an unrequested pile of technology cards.
  const isBlankState = !hasActiveSearch();
  if (els.resultsTrust) els.resultsTrust.hidden = isBlankState;

  if (isBlankState) {
    els.results.innerHTML = `
      <div class="empty-state browse-prompt browse-prompt-compact">
        <span class="browse-prompt-kicker">Ready to explore</span>
        <p>Enter a keyword above, choose a suggested search, or browse the <a href="#sources">source platforms</a>.</p>
      </div>`;
    els.summary.textContent = "Explore technology information indexed from source platforms.";
  } else {
    const redirectHtml = redirectSources.map(redirectSourceBlock).join("");
    const gridHtml = renderMergedGrid(merged.items, merged.searchMode);
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
  const searchableSourceCount = filterableIds.length;
  updateStatsBar(merged.totalAcrossSources, searchableSourceCount, totalCountries);
  updateSearchMethodNote(merged.searchMode, merged.totalAcrossSources);
  if (!isBlankState) {
    els.title.textContent = state.query
      ? `${merged.totalAcrossSources.toLocaleString()} results for "${state.query}"`
      : state.focusTheme
        ? `${merged.totalAcrossSources.toLocaleString()} ${focusLabel || "featured"} technologies`
        : `${merged.totalAcrossSources.toLocaleString()} matching records`;
    const redirectSummary = redirectSources.length
      ? ` · ${redirectSources.length.toLocaleString()} external search`
      : "";
    els.summary.textContent = `${searchableSourceCount.toLocaleString()} searchable catalogue${searchableSourceCount === 1 ? "" : "s"} · ${totalCountries.toLocaleString()} countr${totalCountries === 1 ? "y" : "ies"}${redirectSummary}`;
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
        updateStatsBar(combinedTotal, searchableSourceCount, totalCountries);
        if (hasActiveSearch()) {
          els.title.textContent = state.query
            ? `${combinedTotal.toLocaleString()} results for "${state.query}"`
            : state.focusTheme
              ? `${combinedTotal.toLocaleString()} ${focusLabel || "featured"} technologies`
              : `${combinedTotal.toLocaleString()} matching records`;
        }
      })
      .catch(() => {});
  }
}

async function changeMergedPage(page) {
  state.mergedPage = page;
  analytics?.trackPagination(page);
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
    searchHint: "Search in English. The reviewed snapshot preserves the original Thai metadata and provides English text where translation has been verified.",
  },
  jst_japan: {
    flag: "🇯🇵",
    size: "303",
    sizeValue: 303,
    sizeLabel: "patents",
    description: "Japan Science and Technology Agency (JST) patent portfolio — patents from Japanese universities and public research institutes explicitly available for international licensing across 14 technology categories.",
    coverage: "Japan — patents from JST-funded research institutions covering biotech, materials, semiconductors, energy, medical devices, software, robotics, and more. Granted patents link to JST-hosted documents; applications without a JST PDF use Google Patents as a discovery aid.",
    searchHint: "Search by technology name, inventor, or category. Confirm current status and licensing availability with JST; licensing enquiries go to license@jst.go.jp.",
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
  malaysia_rd_portal: {
    flag: "🇲🇾",
    sizeLabel: "R&D products and technologies",
    description: "Public R&D product and technology records presented through Malaysia's R&D Commercialisation Portal. The Gateway indexes non-contact metadata only and directs users to the original portal for current details and enquiries.",
    coverage: "Malaysia — R&D products and technologies from companies, universities, research institutes, and public agencies represented through the MySTI and Malaysia Commercialisation Year programmes.",
    searchHint: "Search by product or technology name, description, provider, application area, or portal category. Open the original portal record for current commercialisation and contact information.",
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
  const indexedDate = formatIndexedDate(source.last_indexed);
  const provenance = [source.access_method, indexedDate ? `Last indexed ${indexedDate}` : ""]
    .filter(Boolean)
    .join(" · ");
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

      ${provenance ? `<p class="sdc-provenance">${escapeHtml(provenance)}</p>` : ""}

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
          ? `<a class="button button-primary" data-analytics-outbound="external_search" data-analytics-source="${sourceId}" href="${escapeHtml(sourceUrl)}" target="_blank" rel="noopener noreferrer">Search original database ↗</a>`
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
        trackFilterAnalytics("country", state.countries, next);
        state.countries = next;
        state.mergedPage = 1;
        scheduleFilterRender();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.sectorMs,
      sectorOptions,
      () => state.sectors,
      (next) => {
        trackFilterAnalytics("sector", state.sectors, next);
        state.sectors = next;
        state.mergedPage = 1;
        scheduleFilterRender();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.dbtypeMs,
      databaseTypeOptions,
      () => state.databaseTypes,
      (next) => {
        trackFilterAnalytics("database_type", state.databaseTypes, next);
        state.databaseTypes = next;
        state.mergedPage = 1;
        scheduleFilterRender();
      },
      { defaultOpen: true }
    );
    initMultiselect(
      els.sourceMs,
      sourceOptions,
      () => state.sources,
      (next) => {
        trackFilterAnalytics("source", state.sources, next);
        state.sources = next;
        state.mergedPage = 1;
        scheduleFilterRender();
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
  cancelScheduledFilterRender();
  state.query = query.trim();
  state.mergedPage = 1;  // reset pagination on new search
  els.input.value = state.query;
  switchAppView("view-search");
  renderResults();
  document.querySelector("#search-results").scrollIntoView({ behavior: "smooth" });
}

function selectOnlySource(sourceId) {
  trackFilterAnalytics("source", state.sources, [sourceId]);
  state.sources = [sourceId];
  els.sourceMs._render?.();
  runSearch(state.query || "");
}

window.selectOnlySource = selectOnlySource;

els.form.addEventListener("submit", (event) => {
  event.preventDefault();
  recordTrackedTopicSearch(els.input.value);
  trackSearchAnalytics(els.input.value, "search_form");
  runSearch(els.input.value);
});

document.querySelector("#focus-theme-chips")?.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-focus]");
  if (!chip) return;
  const nextTheme = chip.dataset.focus || "";
  analytics?.trackFilter(
    "featured_theme",
    nextTheme ? "select" : "clear",
    nextTheme || "all-technologies",
    nextTheme ? 1 : 0
  );
  state.focusTheme = nextTheme;
  state.mergedPage = 1;
  cancelScheduledFilterRender();
  renderResults();
  document.querySelector("#search-results").scrollIntoView({ behavior: "smooth" });
});

els.clear.addEventListener("click", () => {
  cancelScheduledFilterRender();
  state.query = "";
  state.countries = [];
  state.sectors = [];
  state.databaseTypes = [];
  state.sources = [];
  state.focusTheme = "";
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
  } else if (filterType === "focusTheme") {
    state.focusTheme = "";
  } else if (Array.isArray(state[filterType])) {
    const next = state[filterType].filter((value) => value !== filterValue);
    trackFilterAnalytics(filterType, state[filterType], next);
    state[filterType] = next;
  }
  state.mergedPage = 1;
  cancelScheduledFilterRender();
  syncFacetControls();
  renderResults();
});

const mobileFilterMedia = window.matchMedia("(max-width: 900px)");
let filterSheetReturnFocus = null;

function syncFilterSheetAccessibility() {
  const isMobile = mobileFilterMedia.matches;
  const isOpen = isMobile && els.filters.classList.contains("open");
  if (isMobile) {
    els.filters.setAttribute("role", "dialog");
    els.filters.setAttribute("aria-modal", "true");
    setElementInert(els.filters, !isOpen);
    els.filters.setAttribute("aria-hidden", String(!isOpen));
  } else {
    els.filters.removeAttribute("role");
    els.filters.removeAttribute("aria-modal");
    setElementInert(els.filters, false);
    els.filters.removeAttribute("aria-hidden");
    els.filters.classList.remove("open");
    els.filterBackdrop.classList.remove("visible");
    els.filterBackdrop.hidden = true;
    setElementInert(els.compareTray, els.comparePage.classList.contains("open"));
    document.body.classList.remove("filter-drawer-open");
  }
  els.mobileFilterButton?.setAttribute("aria-expanded", String(isOpen));
}

function openFilterSheet() {
  filterSheetReturnFocus = document.activeElement;
  syncFacetControls();
  els.filters.classList.add("open");
  setElementInert(els.filters, false);
  els.filters.setAttribute("aria-hidden", "false");
  els.mobileFilterButton?.setAttribute("aria-expanded", "true");
  els.filterBackdrop.hidden = false;
  setElementInert(els.compareTray, true);
  document.body.classList.add("filter-drawer-open");
  requestAnimationFrame(() => {
    els.filterBackdrop.classList.add("visible");
    els.filters.querySelector(".filter-close")?.focus();
  });
}

function closeFilterSheet() {
  const wasOpen = els.filters.classList.contains("open");
  els.filters.classList.remove("open");
  setElementInert(els.filters, mobileFilterMedia.matches);
  if (mobileFilterMedia.matches) els.filters.setAttribute("aria-hidden", "true");
  els.mobileFilterButton?.setAttribute("aria-expanded", "false");
  els.filterBackdrop.classList.remove("visible");
  setElementInert(els.compareTray, els.comparePage.classList.contains("open"));
  document.body.classList.remove("filter-drawer-open");
  setTimeout(() => {
    if (!els.filters.classList.contains("open")) els.filterBackdrop.hidden = true;
  }, 200);
  if (wasOpen && filterSheetReturnFocus instanceof HTMLElement && filterSheetReturnFocus.isConnected) {
    filterSheetReturnFocus.focus();
  }
  filterSheetReturnFocus = null;
}

els.mobileFilterButton.addEventListener("click", openFilterSheet);
document.querySelector(".filter-close").addEventListener("click", closeFilterSheet);
els.filterBackdrop.addEventListener("click", closeFilterSheet);
mobileFilterMedia.addEventListener?.("change", syncFilterSheetAccessibility);
syncFilterSheetAccessibility();

els.resetFilters.addEventListener("click", () => {
  cancelScheduledFilterRender();
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

document.addEventListener("click", (event) => {
  const outbound = event.target.closest("[data-analytics-outbound]");
  if (!outbound) return;
  analytics?.trackOutbound(
    outbound.dataset.analyticsOutbound,
    outbound.dataset.analyticsSource
  );
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
        ${source.access_method ? `<p class="sp-provenance">${escapeHtml(source.access_method)}${formatIndexedDate(source.last_indexed) ? ` · Last indexed ${escapeHtml(formatIndexedDate(source.last_indexed))}` : ""}</p>` : ""}
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
      ${safeSourceUrl ? `<a class="button ${isRedirect ? "button-primary" : "button-secondary"}" data-analytics-outbound="source_homepage" data-analytics-source="${safeSourceId}" href="${escapeHtml(safeSourceUrl)}" target="_blank" rel="noopener noreferrer">
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
  if (event.target.closest("[data-clear-query]")) {
    state.query = "";
    state.mergedPage = 1;
    els.input.value = "";
    renderResults();
    els.input.focus();
    return;
  }

  const compareToggle = event.target.closest("[data-compare-toggle]");
  if (compareToggle) {
    toggleComparedItem(compareToggle.dataset.compareToggle);
    return;
  }

  const compareRemove = event.target.closest("[data-compare-remove]");
  if (compareRemove) {
    removeComparedItem(compareRemove.dataset.compareRemove);
    return;
  }

  if (event.target.closest("[data-compare-clear]")) {
    saveCompareItems([]);
    renderCompareTray();
    if (els.comparePage.classList.contains("open")) renderComparePage();
    announceCompare("Comparison cleared.");
    return;
  }

  if (event.target.closest("[data-compare-tray-toggle]")) {
    state.compareTrayCollapsed = !state.compareTrayCollapsed;
    renderCompareTray();
    return;
  }

  if (event.target.closest("[data-compare-open]")) {
    openComparePage();
    return;
  }

  if (event.target.closest("[data-compare-close]")) {
    closeComparePage();
    return;
  }

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
  if (mobileFilterMedia.matches && els.filters.classList.contains("open")) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeFilterSheet();
      return;
    }
    if (event.key === "Tab") {
      const focusable = [...els.filters.querySelectorAll(
        'input:not([disabled]), button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )].filter((element) => !element.hidden && element.getClientRects().length);
      if (focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    return;
  }

  if (els.comparePage.classList.contains("open")) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeComparePage();
      return;
    }
    if (event.key === "Tab") {
      const focusable = [...els.comparePage.querySelectorAll(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )].filter((element) => !element.hidden);
      if (focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    return;
  }

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

renderCompareTray();
renderSourcesTable().then(() => {
  renderResults();
  // Check if URL has a source hash on load
  const match = location.hash.match(/^#source\/(.+)$/);
  if (match) openSourcePage(decodeURIComponent(match[1]), { pushHistory: false });
});
