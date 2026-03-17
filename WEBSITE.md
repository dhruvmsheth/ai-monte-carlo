# Website

The `website/` directory contains a self-contained static site for the project article. No build step is required.

## Local Development

Serve the `website/` directory with any static file server:

```bash
# Python (built-in)
cd website && python3 -m http.server 8080

# Node (npx)
npx serve website -p 8080
```

Then open http://localhost:8080.

## Structure

```
website/
  index.html              # Main article page
  css/style.css           # Stylesheet
  county-map-embed.html   # Animated county build map (p5.js, self-contained)
  embeds/
    baseline-map.html     # 2025 data center snapshot (p5.js)
    growth-chart.html     # MC growth trajectories with play/pause (p5.js)
    scenario-snapshots.html  # 2035 end-state comparison (p5.js)
    cost-benefit.html     # Community surplus vs firm cost (p5.js)
    map_108_training.html    # 108 training counties (Plotly)
    map_232_fractracker.html # 232 FracTracker counties (Plotly)
    full_approval_map.html   # Full 3,153 county approval map (Plotly)
  data/                   # JSON data files (used by js/ sketches)
  js/                     # p5.js sketch files (legacy, embeds are self-contained)
```

All embeds are self-contained HTML files with inlined data and libraries. They work as standalone files or embedded via iframes.

## Deploy to Vercel

1. Push to GitHub (the repo already has `vercel.json` configured).
2. Go to https://vercel.com/new and import the GitHub repository.
3. Vercel auto-detects `vercel.json` and serves `website/` as the root.
4. No build command or framework needed - it's a static site.

Alternatively, deploy from CLI:

```bash
npm i -g vercel
vercel --prod
```

## Notes

- The Plotly map embeds (map_108_training, map_232_fractracker, full_approval_map) are 6-7 MB each because they inline the full plotly.js library. They load lazily via iframe toggle buttons.
- All p5.js embeds are under 400 KB each.
- The site is ~23 MB total, well within Vercel's 100 MB static deployment limit.
