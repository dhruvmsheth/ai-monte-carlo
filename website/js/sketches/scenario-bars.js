/**
 * Scenario Comparison — horizontal bar chart (light theme).
 */
(() => {
  const CONTAINER_ID = "comparison-container";
  const SCENARIOS = ["s1", "s2", "s3", "s4", "s5"];
  const PAD = { top: 20, right: 30, bottom: 20, left: 155 };

  let summary = null;
  let animProgress = 0;
  let canvasW, canvasH;

  const METRICS = [
    { key: "total_built",         label: "Facilities Built",      format: v => v.toFixed(0) },
    { key: "cumulative_gw",       label: "Cumulative GW",         format: v => v.toFixed(1) + " GW" },
    { key: "gini_coefficient",    label: "Gini (Concentration)",  format: v => v.toFixed(3) },
    { key: "community_surplus_m", label: "Community Surplus",     format: v => "$" + (v / 1e6).toFixed(1) + "T" },
    { key: "firm_cost_m",         label: "Firm Cost",             format: v => v < 1 ? "$0" : "$" + (v / 1e3).toFixed(1) + "B" },
  ];

  const sketch = (p) => {
    p.setup = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(480, METRICS.length * 100 + PAD.top + PAD.bottom);
      p.createCanvas(canvasW, canvasH).parent(CONTAINER_ID);
      p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    };

    p.draw = () => {
      if (!summary) return;
      p.background(253);
      animProgress = Math.min(1, animProgress + 0.018);

      const plotW = canvasW - PAD.left - PAD.right;
      const sectionH = (canvasH - PAD.top - PAD.bottom) / METRICS.length;
      const barH = Math.min(12, (sectionH - 28) / SCENARIOS.length);

      p.push();
      p.translate(PAD.left, PAD.top);

      for (let m = 0; m < METRICS.length; m++) {
        const metric = METRICS[m];
        const yBase = m * sectionH;

        p.noStroke();
        p.fill(17);
        p.textAlign(p.RIGHT, p.TOP);
        p.textSize(11);
        p.textStyle(p.BOLD);
        p.text(metric.label, -12, yBase + 2);
        p.textStyle(p.NORMAL);

        let maxVal = 0;
        for (const sid of SCENARIOS) {
          const hi = summary[sid]?.[metric.key]?.p97_5 || summary[sid]?.[metric.key]?.mean || 0;
          maxVal = Math.max(maxVal, hi);
        }
        if (maxVal === 0) maxVal = 1;

        for (let s = 0; s < SCENARIOS.length; s++) {
          const sid = SCENARIOS[s];
          const col = window.COLORS[sid];
          const val = summary[sid]?.[metric.key]?.mean || 0;
          const lo = summary[sid]?.[metric.key]?.p2_5 || 0;
          const hi = summary[sid]?.[metric.key]?.p97_5 || val;
          const yy = yBase + 20 + s * (barH + 3);
          const barW = (val / maxVal) * plotW * animProgress;
          const errLo = (lo / maxVal) * plotW * animProgress;
          const errHi = (hi / maxVal) * plotW * animProgress;
          const midY = yy + barH / 2;

          // Bar
          p.noStroke();
          p.fill(col[0], col[1], col[2], 180);
          p.rect(0, yy, barW, barH, 0, 3, 3, 0);

          // Error bar
          p.stroke(col[0], col[1], col[2], 80);
          p.strokeWeight(1);
          p.line(errLo, midY, errHi, midY);
          p.line(errLo, midY - 2.5, errLo, midY + 2.5);
          p.line(errHi, midY - 2.5, errHi, midY + 2.5);

          // Value
          p.noStroke();
          p.fill(80);
          p.textAlign(p.LEFT, p.CENTER);
          p.textSize(9);
          p.text(metric.format(val), errHi + 5, midY);

          // Scenario label
          p.fill(col[0], col[1], col[2]);
          p.textAlign(p.RIGHT, p.CENTER);
          p.textSize(9);
          p.text(sid.toUpperCase(), -48, midY);
        }

        if (m < METRICS.length - 1) {
          p.stroke(230);
          p.strokeWeight(0.5);
          p.line(-PAD.left + 20, yBase + sectionH - 2, plotW, yBase + sectionH - 2);
        }
      }

      p.pop();
      if (animProgress >= 1) p.noLoop();
    };

    p.windowResized = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(480, METRICS.length * 100 + PAD.top + PAD.bottom);
      p.resizeCanvas(canvasW, canvasH);
      p.loop();
    };
  };

  window.addEventListener("dataReady", () => {
    summary = window.DATA.summary;
    new p5(sketch);
  });
})();
