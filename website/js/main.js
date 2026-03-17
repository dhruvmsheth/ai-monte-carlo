/**
 * Main controller: scroll reveal, data loading, shared state.
 */

// ============ GLOBAL DATA STORE ============
window.DATA = {};

// Scenario colors — darker/saturated for light backgrounds
window.COLORS = {
  s1: [37, 99, 235],    // blue
  s2: [124, 58, 237],   // purple
  s3: [220, 38, 38],    // red
  s4: [22, 163, 74],    // green
  s5: [217, 119, 6],    // amber
};

window.SCENARIO_NAMES = {
  s1: "S1 — Laissez-Faire",
  s2: "S2 — Majority (50%)",
  s3: "S3 — Supermajority (75%)",
  s4: "S4 — Firm Consent (50%)",
  s5: "S5 — Firm Consent (75%)",
};

// Light theme constants for sketches
window.THEME = {
  bg: [253, 253, 253],
  grid: [230, 230, 230],
  text: [17, 17, 17],
  textDim: [130, 130, 130],
  tooltipBg: [255, 255, 255, 245],
  tooltipBorder: [200, 200, 200],
};

// ============ DATA LOADING ============
async function loadAllData() {
  const [timeseries, summary, counties, distributions, countyBuilds] = await Promise.all([
    fetch("data/timeseries.json").then(r => r.json()),
    fetch("data/summary.json").then(r => r.json()),
    fetch("data/counties.json").then(r => r.json()),
    fetch("data/distributions.json").then(r => r.json()),
    fetch("data/county_builds.json").then(r => r.json()),
  ]);
  window.DATA = { timeseries, summary, counties, distributions, countyBuilds };
  window.dispatchEvent(new Event("dataReady"));
}

// ============ SCROLL REVEAL ============
function setupScrollReveal() {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
        }
      });
    },
    { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
  );
  document.querySelectorAll(".scroll-reveal").forEach((el) => observer.observe(el));
}

// ============ INIT ============
document.addEventListener("DOMContentLoaded", () => {
  setupScrollReveal();
  loadAllData();
});
