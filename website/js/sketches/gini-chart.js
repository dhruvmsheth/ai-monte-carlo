/**
 * Gini Coefficient over time — line chart (light theme).
 */
(() => {
  const CONTAINER_ID = "gini-container";
  const SCENARIOS = ["s1", "s2", "s3", "s4", "s5"];
  const PAD = { top: 35, right: 30, bottom: 50, left: 65 };

  let data = null;
  let animProgress = 0;
  let canvasW, canvasH;

  const sketch = (p) => {
    p.setup = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(340, Math.min(canvasW * 0.45, 420));
      p.createCanvas(canvasW, canvasH).parent(CONTAINER_ID);
      p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    };

    p.draw = () => {
      if (!data) return;
      p.background(253);

      const plotW = canvasW - PAD.left - PAD.right;
      const plotH = canvasH - PAD.top - PAD.bottom;

      let yMin = 1, yMax = 0;
      for (const sid of SCENARIOS) {
        for (const row of data[sid]) {
          yMin = Math.min(yMin, row.gini);
          yMax = Math.max(yMax, row.gini);
        }
      }
      const yRange = yMax - yMin;
      yMin = Math.max(0, yMin - yRange * 0.15);
      yMax = Math.min(1, yMax + yRange * 0.1);

      animProgress = Math.min(1, animProgress + 0.01);
      const vis = Math.floor(120 * animProgress);

      p.push();
      p.translate(PAD.left, PAD.top);

      // Grid
      const nY = 5;
      for (let i = 0; i <= nY; i++) {
        const yy = plotH - (i / nY) * plotH;
        p.stroke(230);
        p.strokeWeight(0.7);
        p.line(0, yy, plotW, yy);
        p.noStroke();
        p.fill(130);
        p.textAlign(p.RIGHT, p.CENTER);
        p.textSize(10);
        p.text((yMin + (yMax - yMin) * i / nY).toFixed(3), -8, yy);
      }

      // X labels
      p.noStroke();
      p.fill(130);
      p.textAlign(p.CENTER, p.TOP);
      p.textSize(10);
      for (let yr = 2026; yr <= 2035; yr++) {
        const m = (yr - 2026) * 12 + 6;
        p.text(yr.toString(), (m / 120) * plotW, plotH + 6);
      }

      // Y label
      p.push();
      p.translate(-50, plotH / 2);
      p.rotate(-p.HALF_PI);
      p.textAlign(p.CENTER, p.CENTER);
      p.textSize(11);
      p.fill(100);
      p.text("Gini Coefficient", 0, 0);
      p.pop();

      // Lines
      for (const sid of SCENARIOS) {
        const ts = data[sid];
        const col = window.COLORS[sid];
        p.stroke(col[0], col[1], col[2]);
        p.strokeWeight(2);
        p.noFill();
        p.beginShape();
        for (let i = 0; i < Math.min(ts.length, vis); i++) {
          const xx = (ts[i].month / 120) * plotW;
          const yy = plotH - ((ts[i].gini - yMin) / (yMax - yMin)) * plotH;
          p.vertex(xx, yy);
        }
        p.endShape();
      }

      // Hover
      const mx = p.mouseX - PAD.left;
      const my = p.mouseY - PAD.top;
      if (mx >= 0 && mx <= plotW && my >= 0 && my <= plotH) {
        const hm = Math.max(1, Math.min(120, Math.round((mx / plotW) * 120)));
        const hx = (hm / 120) * plotW;
        p.stroke(180);
        p.strokeWeight(0.8);
        p.line(hx, 0, hx, plotH);

        const idx = hm - 1;
        const mNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        const tooltipX = hx + 12 > plotW - 130 ? hx - 145 : hx + 12;

        p.noStroke();
        p.fill(255, 255, 255, 248);
        p.rect(tooltipX - 2, 6, 136, 18 + SCENARIOS.length * 17, 4);
        p.stroke(210);
        p.strokeWeight(0.5);
        p.noFill();
        p.rect(tooltipX - 2, 6, 136, 18 + SCENARIOS.length * 17, 4);

        const row0 = data.s1[idx];
        p.noStroke();
        p.fill(17);
        p.textAlign(p.LEFT, p.TOP);
        p.textSize(10);
        p.textStyle(p.BOLD);
        p.text(mNames[row0.cal - 1] + " " + row0.year, tooltipX + 6, 10);
        p.textStyle(p.NORMAL);

        for (let s = 0; s < SCENARIOS.length; s++) {
          const sid = SCENARIOS[s];
          const col = window.COLORS[sid];
          const row = data[sid][idx];
          const ty = 26 + s * 17;
          p.fill(col[0], col[1], col[2]);
          p.noStroke();
          p.circle(tooltipX + 10, ty + 4, 6);
          p.fill(60);
          p.textSize(9);
          p.text(sid.toUpperCase() + ": " + row.gini.toFixed(4), tooltipX + 20, ty);

          const dotY = plotH - ((row.gini - yMin) / (yMax - yMin)) * plotH;
          p.fill(col[0], col[1], col[2]);
          p.circle(hx, dotY, 6);
        }
      }

      p.pop();

      // Legend
      p.textAlign(p.LEFT, p.CENTER);
      p.textSize(10);
      let lx = PAD.left;
      let ly = canvasH - 14;
      for (const sid of SCENARIOS) {
        const col = window.COLORS[sid];
        const name = window.SCENARIO_NAMES[sid];
        const itemW = p.textWidth(name) + 28;
        if (lx + itemW > canvasW - 10) { lx = PAD.left; ly += 14; }
        p.fill(col[0], col[1], col[2]);
        p.noStroke();
        p.rect(lx, ly - 1, 12, 2.5, 1);
        p.fill(100);
        p.text(name, lx + 16, ly);
        lx += itemW;
      }

      if (animProgress >= 1) p.noLoop();
    };

    p.mouseMoved = () => { if (data) p.loop(); };

    p.windowResized = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(340, Math.min(canvasW * 0.45, 420));
      p.resizeCanvas(canvasW, canvasH);
      p.loop();
    };
  };

  window.addEventListener("dataReady", () => {
    data = window.DATA.timeseries;
    new p5(sketch);
  });
})();
