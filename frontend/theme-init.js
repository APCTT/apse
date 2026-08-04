(function initializeGatewayTheme() {
  "use strict";
  const previewParams = new URLSearchParams(window.location.search);
  const previewAllowed = window.location.hostname === "127.0.0.1"
    || window.location.hostname === "localhost";
  const selectedTheme = previewAllowed ? previewParams.get("theme") : null;
  const selectedConcept = previewAllowed ? previewParams.get("concept") : null;
  const useClassicTheme = selectedTheme === "classic";
  const useNetworkConcept = !useClassicTheme && selectedConcept !== "standard";
  const apcttTheme = document.querySelector("#apctt-theme");
  const energyConcept = document.querySelector("#energy-concept");
  if (apcttTheme) apcttTheme.disabled = useClassicTheme;
  if (energyConcept) energyConcept.disabled = !useNetworkConcept;
  document.documentElement.dataset.theme = useClassicTheme ? "classic" : "apctt";
  document.documentElement.dataset.concept = useNetworkConcept ? "network" : "standard";
})();
