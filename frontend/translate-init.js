(function registerGoogleTranslateCallback() {
  "use strict";
  globalThis.googleTranslateElementInit = function googleTranslateElementInit() {
    if (!globalThis.google?.translate?.TranslateElement) return;
    new globalThis.google.translate.TranslateElement(
      {
        pageLanguage: "en",
        includedLanguages:
          "en,ko,ja,zh-CN,hi,th,vi,ms,id,bn,si,ne,ru,tl,km,my,lo,mn,ur,ta,fr",
        layout: globalThis.google.translate.TranslateElement.InlineLayout.SIMPLE,
        autoDisplay: false,
      },
      "google_translate_element"
    );
  };
})();
