(function initAptgAnalytics(root, factory) {
  const analytics = factory(root);
  if (typeof module === "object" && module.exports) module.exports = analytics;
  if (root && root.document) {
    root.AptgAnalytics = analytics;
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", analytics.init, { once: true });
    } else {
      analytics.init();
    }
  }
})(typeof window !== "undefined" ? window : globalThis, function createAnalytics(root) {
  "use strict";

  const MEASUREMENT_ID = "G-MMFLWFWN91";
  const CONSENT_KEY = "aptg_analytics_consent_v1";
  const ALLOWED_HOSTS = new Set(["ap-tg.net", "www.ap-tg.net"]);
  const APPROVED_SEARCH_TOPICS = new Set([
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

  let googleTagStarted = false;
  let banner = null;

  function normalizeText(value) {
    return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
  }

  function queryLengthBucket(value) {
    const length = String(value || "").trim().length;
    if (!length) return "0";
    if (length <= 20) return "1-20";
    if (length <= 50) return "21-50";
    if (length <= 100) return "51-100";
    if (length <= 200) return "101-200";
    return "200+";
  }

  function readConsent() {
    try {
      const value = root.localStorage?.getItem(CONSENT_KEY);
      return value === "granted" || value === "denied" ? value : null;
    } catch {
      return null;
    }
  }

  function storeConsent(value) {
    try {
      root.localStorage?.setItem(CONSENT_KEY, value);
    } catch {
      // The choice still applies for the current page when storage is blocked.
    }
  }

  function isProductionHost() {
    return ALLOWED_HOSTS.has(root.location?.hostname || "");
  }

  function clearAnalyticsCookies() {
    if (!root.document) return;
    const hostname = root.location?.hostname || "";
    root.document.cookie.split(";").forEach((entry) => {
      const name = entry.split("=")[0].trim();
      if (!name.startsWith("_ga")) return;
      root.document.cookie = `${name}=; Max-Age=0; path=/; SameSite=Lax`;
      if (hostname) {
        root.document.cookie = `${name}=; Max-Age=0; path=/; domain=.${hostname}; SameSite=Lax`;
      }
    });
  }

  function configureGoogleTag() {
    root.dataLayer = root.dataLayer || [];
    root.gtag = root.gtag || function gtag() {
      root.dataLayer.push(arguments);
    };
    root.gtag("consent", "default", {
      analytics_storage: "granted",
      ad_storage: "denied",
      ad_user_data: "denied",
      ad_personalization: "denied",
    });
    root.gtag("set", "ads_data_redaction", true);
    root.gtag("js", new Date());
    root.gtag("config", MEASUREMENT_ID, {
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_expires: 60 * 24 * 60 * 60,
      cookie_update: false,
      send_page_view: true,
    });
  }

  function startGoogleTag() {
    if (googleTagStarted || readConsent() !== "granted" || !isProductionHost()) return;
    googleTagStarted = true;
    configureGoogleTag();
    const script = root.document.createElement("script");
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(MEASUREMENT_ID)}`;
    script.dataset.aptgAnalytics = "true";
    root.document.head.appendChild(script);
  }

  function hideBanner() {
    banner?.remove();
    banner = null;
  }

  function setConsent(value) {
    if (value !== "granted" && value !== "denied") return;
    storeConsent(value);
    if (value === "granted") {
      startGoogleTag();
    } else {
      if (typeof root.gtag === "function") {
        root.gtag("consent", "update", {
          analytics_storage: "denied",
          ad_storage: "denied",
          ad_user_data: "denied",
          ad_personalization: "denied",
        });
      }
      clearAnalyticsCookies();
    }
    hideBanner();
  }

  function showBanner() {
    if (!root.document || banner) {
      banner?.querySelector("button")?.focus();
      return;
    }
    banner = root.document.createElement("section");
    banner.className = "analytics-consent-banner";
    banner.setAttribute("role", "dialog");
    banner.setAttribute("aria-modal", "false");
    banner.setAttribute("aria-labelledby", "analytics-consent-title");
    banner.innerHTML = `
      <div class="analytics-consent-copy">
        <strong id="analytics-consent-title">Optional analytics cookies</strong>
        <p>We use optional analytics cookies to understand how the Gateway is used and improve the service. No advertising cookies are used.</p>
        <a href="privacy-notice.html#cookies">Analytics details</a>
      </div>
      <div class="analytics-consent-actions">
        <button type="button" class="button button-secondary" data-analytics-choice="denied">Decline</button>
        <button type="button" class="button button-primary" data-analytics-choice="granted">Accept analytics</button>
      </div>`;
    banner.addEventListener("click", (event) => {
      const button = event.target.closest("[data-analytics-choice]");
      if (button) setConsent(button.dataset.analyticsChoice);
    });
    root.document.body.appendChild(banner);
    banner.querySelector("[data-analytics-choice='granted']")?.focus();
  }

  function sendEvent(name, parameters) {
    if (readConsent() !== "granted" || typeof root.gtag !== "function") return false;
    root.gtag("event", name, parameters);
    return true;
  }

  function trackSearch(term, origin, filterCounts = {}) {
    const normalized = normalizeText(term);
    const parameters = {
      search_origin: String(origin || "unknown").slice(0, 40),
      query_length_bucket: queryLengthBucket(term),
      country_filter_count: Number(filterCounts.countries) || 0,
      sector_filter_count: Number(filterCounts.sectors) || 0,
      source_filter_count: Number(filterCounts.sources) || 0,
      database_type_filter_count: Number(filterCounts.databaseTypes) || 0,
    };
    if (origin === "suggested_topic" && APPROVED_SEARCH_TOPICS.has(normalized)) {
      parameters.search_term = normalized;
      return sendEvent("search", parameters);
    }
    return sendEvent("aptg_search", parameters);
  }

  function trackFilter(filterType, action, value, selectionCount) {
    return sendEvent("aptg_filter_change", {
      filter_type: String(filterType || "unknown").slice(0, 40),
      filter_action: action === "remove" ? "remove" : "add",
      filter_value: String(value || "unknown").slice(0, 100),
      selection_count: Number(selectionCount) || 0,
    });
  }

  function trackOutbound(destinationType, sourceId) {
    return sendEvent("aptg_outbound_click", {
      destination_type: String(destinationType || "external_source").slice(0, 50),
      source_id: String(sourceId || "unknown").slice(0, 80),
    });
  }

  function trackPagination(page) {
    return sendEvent("aptg_results_page", { page_number: Number(page) || 1 });
  }

  function init() {
    root.document.querySelectorAll("[data-analytics-preferences]").forEach((control) => {
      control.addEventListener("click", showBanner);
    });
    const consent = readConsent();
    if (consent === "granted") startGoogleTag();
    if (!consent) showBanner();
  }

  return {
    MEASUREMENT_ID,
    CONSENT_KEY,
    init,
    readConsent,
    setConsent,
    showBanner,
    queryLengthBucket,
    trackSearch,
    trackFilter,
    trackOutbound,
    trackPagination,
  };
});
