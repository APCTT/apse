(function initAptgSecurity(global) {
  "use strict";

  const ESCAPE_MAP = Object.freeze({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  });

  const MOJIBAKE_REPLACEMENTS = Object.freeze([
    ["â€“", "–"],
    ["â€”", "—"],
    ["â€™", "’"],
    ["â€˜", "‘"],
    ["â€œ", "“"],
    ["â€", "”"],
    ["â€¦", "…"],
    ["Â°C", "°C"],
    ["Â ", " "],
  ]);

  function normalizeDisplayText(value) {
    return MOJIBAKE_REPLACEMENTS.reduce(
      (text, [broken, corrected]) => text.replaceAll(broken, corrected),
      String(value ?? "")
    );
  }

  function escapeHtml(value) {
    return normalizeDisplayText(value).replace(
      /[&<>"']/g,
      (character) => ESCAPE_MAP[character]
    );
  }

  function safeExternalUrl(value) {
    const raw = String(value ?? "").trim();
    if (!raw) return "";
    try {
      const parsed = new URL(raw);
      if (!["http:", "https:"].includes(parsed.protocol)) return "";
      // Credentials in outbound links are unnecessary and can disguise the
      // actual destination shown to a user.
      if (parsed.username || parsed.password) return "";
      return parsed.href;
    } catch {
      return "";
    }
  }

  const api = Object.freeze({
    escapeHtml,
    normalizeDisplayText,
    safeExternalUrl,
  });

  global.AptgSecurity = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : window);
