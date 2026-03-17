/**
 * Cost-Benefit — grouped bar chart (light theme).
 */
(() => {
  const CONTAINER_ID = "costbenefit-container";
  const SCENARIOS = ["s1", "s2", "s3", "s4", "s5"];
  const PAD = { top: 45, right: 30, bottom: 65, left: 75 };

  let summary = null;
  let animProgress = 0;
  let canvasW, canvasH;

  const sketch = (p) => {
    p.setup = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(380, Math.min(canvasW * 0.5, 450));
      p.createCanvas(canvasW, canvasH).parent(CONTAINER_ID);
      p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    };

    p.draw = () => {
      if (!summary) return;
      p.background(253);
      animProgress = Math.min(1, animProgress + 0.015);

      const plotW = canvasW - PAD.left - PAD.right;
      const plotH = canvasH - PAD.top - PAD.bottom;

      const surplusVals = [];
      const costVals = [];
      for (const sid of SCENARIOS) {
        surplusVals.push((summary[sid]?.community_surplus_m?.mean || 0) / 1e6);
        costVals.push((summary[sid]?.firm_cost_m?.mean || 0) / 1e3);
      }

      const maxSurplus = Math.max(...surplusVals) * 1.15;

      p.push();
      p.translate(PAD.left, PAD.top);

      // Title
      p.noStroke();
      p.fill(17);
      p.textAlign(p.CENTER, p.BOTTOM);
      p.textSize(12);
      p.textStyle(p.BOLD);
      p.text("Community Surplus vs. Firm Cost", plotW / 2, -10);
      p.textStyle(p.NORMAL);

      // Y grid
      const nT = 5;
      for (let i = 0; i <= nT; i++) {
        const yy = plotH - (i / nT) * plotH;
        p.stroke(230);
        p.strokeWeight(0.7);
        p.line(0, yy, plotW, yy);
        p.noStroke();
        p.fill(130);
        p.textAlign(p.RIGHT, p.CENTER);
        p.textSize(10);
        p.text("$" + (maxSurplus * i / nT).toFixed(1) + "T", -8, yy);
      }

      // Y label
      p.push();
      p.translate(-58, plotH / 2);
      p.rotate(-p.HALF_PI);
      p.fill(100);
      p.textAlign(p.CENTER, p.CENTER);
      p.textSize(11);
      p.text("Community Surplus ($T)", 0, 0);
      p.pop();

      const groupW = plotW / SCENARIOS.length;
      const barW = groupW * 0.5;

      for (let s = 0; s < SCENARIOS.length; s++) {
        const sid = SCENARIOS[s];
        const col = window.COLORS[sid];
        const cx = s * groupW + groupW / 2;
        const surplus = surplusVals[s];
        const cost = costVals[s];
        const barH = (surplus / maxSurplus) * plotH * animProgress;

        // Bar
        p.noStroke();
        p.fill(col[0], col[1], col[2], 180);
        p.rect(cx - barW / 2, plotH - barH, barW, barH, 3, 3, 0, 0);

        // Value
        p.fill(col[0], col[1], col[2]);
        p.textAlign(p.CENTER, p.BOTTOM);
        p.textSize(11);
        p.textStyle(p.BOLD);
        p.text("$" + surplus.toFixed(1) + "T", cx, plotH - barH - 3);
        p.textStyle(p.NORMAL);

        // Firm cost overlay
        if (cost > 0) {
          const costH = (cost / 1000 / maxSurplus) * plotH * animProgress;
          p.fill(220, 50, 50, 120);
          p.rect(cx - barW / 2, plotH - costH, barW, costH);
          p.fill(180, 40, 40);
          p.textAlign(p.CENTER, p.TOP);
          p.textSize(9);
          p.text("Cost: $" + cost.toFixed(1) + "B", cx, plotH + 26);
        }

        // Scenario label
        p.fill(col[0], col[1], col[2]);
        p.textAlign(p.CENTER, p.TOP);
        p.textSize(10);
        p.text(sid.toUpperCase(), cx, plotH + 6);

        // Name
        p.fill(130);
        p.textSize(8);
        const short = window.SCENARIO_NAMES[sid].split("—")[1]?.trim() || sid;
        p.text(short, cx, plotH + 40);
      }

      // ROI annotation for S4
      const s4S = surplusVals[3], s4C = costVals[3];
      if (s4C > 0 && animProgress > 0.5) {
        const roi = Math.round(s4S * 1000 / s4C);
        const cx4 = 3 * groupW + groupW / 2;
        p.fill(22, 163, 74);
        p.textAlign(p.CENTER, p.BOTTOM);
        p.textSize(11);
        p.textStyle(p.BOLD);
        p.text(roi + ":1 return", cx4, plotH - (s4S / maxSurplus) * plotH * animProgress - 18);
        p.textStyle(p.NORMAL);
      }

      p.pop();
      if (animProgress >= 1) p.noLoop();
    };

    p.windowResized = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(380, Math.min(canvasW * 0.5, 450));
      p.resizeCanvas(canvasW, canvasH);
      p.loop();
    };
  };

  window.addEventListener("dataReady", () => {
    summary = window.DATA.summary;
    new p5(sketch);
  });
})();
