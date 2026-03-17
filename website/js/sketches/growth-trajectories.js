/**
 * Growth Trajectories — animated line chart (light theme).
 */
(() => {
  const CONTAINER_ID = "growth-container";
  const SCENARIOS = ["s1", "s2", "s3", "s4", "s5"];
  const PAD = { top: 40, right: 30, bottom: 55, left: 65 };
  const T = window.THEME;

  let data = null;
  let metric = "gw";
  let showCI = true;
  let animProgress = 0;
  let canvasW, canvasH;

  const sketch = (p) => {
    p.setup = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(380, Math.min(canvasW * 0.5, 480));
      p.createCanvas(canvasW, canvasH).parent(CONTAINER_ID);
      p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    };

    p.draw = () => {
      if (!data) return;
      p.background(253);

      const plotW = canvasW - PAD.left - PAD.right;
      const plotH = canvasH - PAD.top - PAD.bottom;
      const key = metric === "gw" ? "gw" : "built";
      const keyHi = metric === "gw" ? "gw_hi" : "built_hi";
      const keyLo = metric === "gw" ? "gw_lo" : "built_lo";

      let yMax = 0;
      for (const sid of SCENARIOS) {
        for (const row of data[sid]) yMax = Math.max(yMax, row[keyHi] || row[key]);
      }
      yMax = Math.ceil(yMax * 1.1);

      if (animProgress < 1) animProgress = Math.min(1, animProgress + 0.01);
      const visibleMonths = Math.floor(120 * animProgress);

      p.push();
      p.translate(PAD.left, PAD.top);

      // Grid
      const nYTicks = 5;
      for (let i = 0; i <= nYTicks; i++) {
        const yy = plotH - (i / nYTicks) * plotH;
        p.stroke(230);
        p.strokeWeight(0.7);
        p.line(0, yy, plotW, yy);
        p.noStroke();
        p.fill(130);
        p.textAlign(p.RIGHT, p.CENTER);
        p.textSize(10);
        const val = yMax * i / nYTicks;
        p.text(metric === "gw" ? val.toFixed(0) + " GW" : val.toFixed(0), -8, yy);
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

      // Y-axis label
      p.push();
      p.translate(-50, plotH / 2);
      p.rotate(-p.HALF_PI);
      p.textAlign(p.CENTER, p.CENTER);
      p.textSize(11);
      p.fill(100);
      p.text(metric === "gw" ? "Cumulative Capacity (GW)" : "Facilities Built", 0, 0);
      p.pop();

      // CI bands + lines
      for (const sid of SCENARIOS) {
        const ts = data[sid];
        const col = window.COLORS[sid];

        if (showCI) {
          p.fill(col[0], col[1], col[2], 20);
          p.noStroke();
          p.beginShape();
          for (let i = 0; i < Math.min(ts.length, visibleMonths); i++) {
            p.vertex((ts[i].month / 120) * plotW, plotH - (ts[i][keyHi] / yMax) * plotH);
          }
          for (let i = Math.min(ts.length, visibleMonths) - 1; i >= 0; i--) {
            p.vertex((ts[i].month / 120) * plotW, plotH - (ts[i][keyLo] / yMax) * plotH);
          }
          p.endShape(p.CLOSE);
        }

        p.stroke(col[0], col[1], col[2]);
        p.strokeWeight(2);
        p.noFill();
        p.beginShape();
        for (let i = 0; i < Math.min(ts.length, visibleMonths); i++) {
          p.vertex((ts[i].month / 120) * plotW, plotH - (ts[i][key] / yMax) * plotH);
        }
        p.endShape();
      }

      // Hover
      const mx = p.mouseX - PAD.left;
      const my = p.mouseY - PAD.top;
      if (mx >= 0 && mx <= plotW && my >= 0 && my <= plotH) {
        let hoverMonth = Math.max(1, Math.min(120, Math.round((mx / plotW) * 120)));
        const hx = (hoverMonth / 120) * plotW;

        p.stroke(180);
        p.strokeWeight(0.8);
        p.line(hx, 0, hx, plotH);

        const idx = hoverMonth - 1;
        const row0 = data.s1[idx];
        const mNames = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
        const tooltipX = hx + 12 > plotW - 155 ? hx - 168 : hx + 12;

        // Tooltip background
        p.noStroke();
        p.fill(255, 255, 255, 248);
        p.rect(tooltipX - 2, 6, 162, 22 + SCENARIOS.length * 19, 4);
        p.stroke(210);
        p.strokeWeight(0.5);
        p.noFill();
        p.rect(tooltipX - 2, 6, 162, 22 + SCENARIOS.length * 19, 4);

        p.noStroke();
        p.fill(17);
        p.textAlign(p.LEFT, p.TOP);
        p.textSize(11);
        p.textStyle(p.BOLD);
        p.text(mNames[row0.cal - 1] + " " + row0.year, tooltipX + 6, 10);
        p.textStyle(p.NORMAL);

        for (let s = 0; s < SCENARIOS.length; s++) {
          const sid = SCENARIOS[s];
          const col = window.COLORS[sid];
          const row = data[sid][idx];
          const val = row ? row[key] : 0;

          const dotY = plotH - (val / yMax) * plotH;
          p.fill(col[0], col[1], col[2]);
          p.noStroke();
          p.circle(hx, dotY, 7);

          const ty = 28 + s * 19;
          p.fill(col[0], col[1], col[2]);
          p.circle(tooltipX + 10, ty + 5, 7);
          p.fill(60);
          p.textSize(10);
          p.text(sid.toUpperCase() + ": " + (metric === "gw" ? val.toFixed(1) + " GW" : val.toFixed(0)), tooltipX + 20, ty);
        }
      }

      p.pop();

      // Legend
      p.textAlign(p.LEFT, p.CENTER);
      p.textSize(10);
      let lx = PAD.left;
      let ly = canvasH - 16;
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
      canvasH = Math.max(380, Math.min(canvasW * 0.5, 480));
      p.resizeCanvas(canvasW, canvasH);
      p.loop();
    };
  };

  window.addEventListener("dataReady", () => {
    data = window.DATA.timeseries;
    document.getElementById("growth-metric").addEventListener("change", (e) => {
      metric = e.target.value;
      animProgress = 0;
      document.getElementById(CONTAINER_ID)._p5?.loop();
    });
    document.getElementById("growth-show-ci").addEventListener("change", (e) => {
      showCI = e.target.checked;
      document.getElementById(CONTAINER_ID)._p5?.loop();
    });
    const inst = new p5(sketch);
    document.getElementById(CONTAINER_ID)._p5 = inst;
  });
})();
