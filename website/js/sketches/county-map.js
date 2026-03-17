/**
 * County Map — interactive dot map (light theme).
 * Warm-toned map on light background.
 */
(() => {
  const CONTAINER_ID = "map-container";
  const PAD = { top: 10, right: 10, bottom: 36, left: 10 };
  const LON_MIN = -125, LON_MAX = -66, LAT_MIN = 24.5, LAT_MAX = 49.5;

  let counties = null;
  let builds = null;
  let countyByFips = {};
  let scenario = "s4";
  let targetMonth = 6;
  let playing = false;
  let playTimer = 0;
  let canvasW, canvasH;

  function approvalColor(prob) {
    const stops = [
      [0.00, 180,  30,  30],  // muted red
      [0.30, 210, 120,  40],  // orange
      [0.50, 190, 170,  70],  // dull yellow
      [0.70, 100, 160,  80],  // olive green
      [1.00,  30, 120,  55],  // forest green
    ];
    const t = Math.max(0, Math.min(1, (prob - 0.05) / 0.9));
    let lo = stops[0], hi = stops[stops.length - 1];
    for (let i = 0; i < stops.length - 1; i++) {
      if (t >= stops[i][0] && t <= stops[i + 1][0]) { lo = stops[i]; hi = stops[i + 1]; break; }
    }
    const f = (hi[0] === lo[0]) ? 0 : (t - lo[0]) / (hi[0] - lo[0]);
    return [lo[1] + (hi[1] - lo[1]) * f, lo[2] + (hi[2] - lo[2]) * f, lo[3] + (hi[3] - lo[3]) * f];
  }

  function lonToX(lon) {
    return PAD.left + ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * (canvasW - PAD.left - PAD.right);
  }
  function latToY(lat) {
    return PAD.top + ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * (canvasH - PAD.top - PAD.bottom);
  }

  const MNAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

  function updateMonthLabel() {
    const yr = 2026 + Math.floor((targetMonth - 1) / 12);
    const m = (targetMonth - 1) % 12;
    document.getElementById("map-month-label").textContent =
      MNAMES[m] + " " + yr + " (Month " + targetMonth + ")";
  }

  const sketch = (p) => {
    p.setup = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(380, Math.min(canvasW * 0.55, 500));
      p.createCanvas(canvasW, canvasH).parent(CONTAINER_ID);
      p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
      p.noLoop();
    };

    p.draw = () => {
      if (!counties) return;
      p.background(248, 248, 246);

      // Background dots
      p.noStroke();
      for (const c of counties) {
        const col = approvalColor(c.p);
        p.fill(col[0], col[1], col[2], 110);
        p.circle(lonToX(c.x), latToY(c.y), 3);
      }

      // Build circles
      const snap = builds?.[scenario]?.[String(targetMonth)];
      if (snap) {
        let maxB = 0;
        for (const fips in snap) maxB = Math.max(maxB, snap[fips]);

        for (const fips in snap) {
          const c = countyByFips[fips];
          if (!c) continue;
          const count = snap[fips];
          const size = 5 + 24 * Math.sqrt(count / Math.max(maxB, 1));
          p.fill(37, 99, 235, 160);
          p.stroke(37, 99, 235, 80);
          p.strokeWeight(0.5);
          p.circle(lonToX(c.x), latToY(c.y), size);
        }
      }

      // Stats overlay
      const ts = window.DATA.timeseries[scenario];
      const row = ts[Math.min(targetMonth - 1, ts.length - 1)];
      p.noStroke();
      p.fill(255, 255, 255, 235);
      p.rect(canvasW - 210, 8, 200, 72, 5);
      p.stroke(210);
      p.strokeWeight(0.5);
      p.noFill();
      p.rect(canvasW - 210, 8, 200, 72, 5);
      p.noStroke();
      p.fill(17);
      p.textAlign(p.LEFT, p.TOP);
      p.textSize(12);
      p.textStyle(p.BOLD);
      p.text(MNAMES[row.cal - 1] + " " + row.year, canvasW - 200, 14);
      p.textStyle(p.NORMAL);
      p.textSize(10);
      p.fill(80);
      p.text("Built: " + row.built.toFixed(0) + " facilities", canvasW - 200, 32);
      p.text("Capacity: " + row.gw.toFixed(1) + " GW", canvasW - 200, 46);
      p.text("Gini: " + row.gini.toFixed(3), canvasW - 200, 60);

      // Color legend
      p.textAlign(p.LEFT, p.CENTER);
      p.textSize(9);
      p.fill(130);
      p.noStroke();
      p.text("Low approval", 10, canvasH - 12);
      for (let i = 0; i < 70; i++) {
        const col = approvalColor(0.05 + (i / 69) * 0.9);
        p.stroke(col[0], col[1], col[2]);
        p.line(82 + i, canvasH - 18, 82 + i, canvasH - 7);
      }
      p.noStroke();
      p.fill(130);
      p.text("High", 156, canvasH - 12);

      p.fill(37, 99, 235, 160);
      p.noStroke();
      p.circle(200, canvasH - 12, 8);
      p.fill(130);
      p.text("= Facilities built", 208, canvasH - 12);

      // Animation
      if (playing) {
        playTimer++;
        if (playTimer % 6 === 0) {
          targetMonth += 6;
          if (targetMonth > 120) {
            targetMonth = 6;
            playing = false;
            document.getElementById("map-play-btn").innerHTML = "&#9654; Play";
          }
          document.getElementById("map-month-slider").value = targetMonth;
          updateMonthLabel();
        }
        p.loop();
      } else {
        p.noLoop();
      }
    };

    p.windowResized = () => {
      const container = document.getElementById(CONTAINER_ID);
      canvasW = container.clientWidth;
      canvasH = Math.max(380, Math.min(canvasW * 0.55, 500));
      p.resizeCanvas(canvasW, canvasH);
      p.redraw();
    };
  };

  window.addEventListener("dataReady", () => {
    counties = window.DATA.counties;
    builds = window.DATA.countyBuilds;
    countyByFips = {};
    for (const c of counties) countyByFips[c.f] = c;

    const inst = new p5(sketch);
    document.getElementById(CONTAINER_ID)._p5 = inst;

    document.getElementById("map-scenario").addEventListener("change", (e) => {
      scenario = e.target.value;
      inst.redraw();
    });
    document.getElementById("map-month-slider").addEventListener("input", (e) => {
      targetMonth = parseInt(e.target.value);
      updateMonthLabel();
      inst.redraw();
    });
    document.getElementById("map-play-btn").addEventListener("click", () => {
      playing = !playing;
      document.getElementById("map-play-btn").innerHTML = playing ? "&#9724; Pause" : "&#9654; Play";
      if (playing) {
        if (targetMonth >= 120) targetMonth = 6;
        inst.loop();
      }
    });
    updateMonthLabel();
  });
})();
