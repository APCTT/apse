(function registerGoogleTranslateCallback() {
  "use strict";

  const COOKIE_NAME = "googtrans";
  const selectId = "site-language-select";

  function selectedLanguageFromCookie() {
    const match = document.cookie.match(/(?:^|;\s*)googtrans=\/en\/([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "en";
  }

  function syncLanguageControl() {
    const select = document.getElementById(selectId);
    if (!select) return;
    const language = selectedLanguageFromCookie();
    if ([...select.options].some((option) => option.value === language)) {
      select.value = language;
    }
  }

  function setTranslationCookie(language) {
    document.cookie = `${COOKIE_NAME}=/en/${language};path=/;SameSite=Lax`;
  }

  function applyLanguage(language) {
    setTranslationCookie(language);
    const googleSelect = document.querySelector(".goog-te-combo");
    if (googleSelect && [...googleSelect.options].some((option) => option.value === language)) {
      googleSelect.value = language;
      googleSelect.dispatchEvent(new Event("change"));
      return;
    }
    // If Google's embedded engine is unavailable in production, use its
    // official website-translation route instead of leaving a dead control.
    const localPreview = ["localhost", "127.0.0.1"].includes(window.location.hostname);
    if (language !== "en" && !localPreview) {
      const translatedUrl =
        `https://translate.google.com/translate?sl=en&tl=${encodeURIComponent(language)}` +
        `&u=${encodeURIComponent(window.location.href)}`;
      window.location.assign(translatedUrl);
      return;
    }
    // Google cannot fetch a localhost page. Reload local previews so the
    // selected state can still be checked without navigating to a broken URL.
    window.location.reload();
  }

  function registerLanguageControl() {
    const select = document.getElementById(selectId);
    if (!select || select.dataset.ready === "true") return;
    select.dataset.ready = "true";
    syncLanguageControl();
    select.addEventListener("change", () => applyLanguage(select.value));
  }

  globalThis.googleTranslateElementInit = function googleTranslateElementInit() {
    if (!globalThis.google?.translate?.TranslateElement) return;
    new globalThis.google.translate.TranslateElement(
      {
        pageLanguage: "en",
        includedLanguages:
          "en,ko,ja,zh-CN,hi,th,vi,ms,id,bn,si,ne,ru,tl,km,my,lo,mn,ur,ta,fr",
        layout: globalThis.google.translate.TranslateElement.InlineLayout.HORIZONTAL,
        autoDisplay: false,
      },
      "google_translate_element"
    );
    syncLanguageControl();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", registerLanguageControl, { once: true });
  } else {
    registerLanguageControl();
  }
})();
