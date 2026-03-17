#!/usr/bin/env python3
"""Build a self-contained HTML embed for the interactive county map.

Inlines compacted data + p5.js sketch into a single HTML block
suitable for pasting into a Wix HTML embed widget.
"""
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
WEBSITE_DATA = PROJECT / "website" / "data"
OUT = PROJECT / "website" / "county-map-embed.html"


def compact_counties(counties: list[dict]) -> list:
    """Compact county data: [fips, lon, lat, prob] arrays."""
    return [[c["f"], round(c["x"], 2), round(c["y"], 2), round(c["p"], 3)] for c in counties]


def compact_builds(builds: dict, step: int = 12) -> dict:
    """Keep only every `step` months, prune small values."""
    result = {}
    for sid, snapshots in builds.items():
        result[sid] = {}
        for month_str, county_data in snapshots.items():
            m = int(month_str)
            if m % step == 0:
                # Only keep counties with meaningful build counts
                result[sid][month_str] = {
                    fips: round(v, 1) for fips, v in county_data.items()
                    if v >= 0.3
                }
    return result


def compact_timeseries(ts: dict) -> dict:
    """Keep only fields needed for the stats overlay."""
    result = {}
    for sid, rows in ts.items():
        result[sid] = [
            {"m": r["month"], "yr": r["year"], "cal": r["cal"],
             "b": r["built"], "gw": r["gw"], "gi": r["gini"], "fc": r["firm_cost"]}
            for r in rows
        ]
    return result


def main():
    with open(WEBSITE_DATA / "counties.json") as f:
        counties_raw = json.load(f)
    with open(WEBSITE_DATA / "county_builds.json") as f:
        builds_raw = json.load(f)
    with open(WEBSITE_DATA / "timeseries.json") as f:
        ts_raw = json.load(f)

    counties = compact_counties(counties_raw)
    builds = compact_builds(builds_raw, step=12)  # keep every 12 months
    ts = compact_timeseries(ts_raw)

    counties_json = json.dumps(counties, separators=(",", ":"))
    builds_json = json.dumps(builds, separators=(",", ":"))
    ts_json = json.dumps(ts, separators=(",", ":"))

    print(f"Counties: {len(counties_json)//1024}KB")
    print(f"Builds: {len(builds_json)//1024}KB")
    print(f"Timeseries: {len(ts_json)//1024}KB")
    total = len(counties_json) + len(builds_json) + len(ts_json)
    print(f"Total inline data: {total//1024}KB")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: #fdfdfd; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif; color: #111; }}
#wrapper {{ max-width: 900px; margin: 0 auto; padding: 16px; }}
h2 {{ font-family: "Palatino", "Palatino Linotype", Georgia, serif; font-weight: 400; font-size: 1.8rem; margin-bottom: 8px; }}
p.desc {{ font-family: "Palatino", "Palatino Linotype", Georgia, serif; font-size: 1rem; color: #555; line-height: 1.6; margin-bottom: 12px; }}
.controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 8px; font-size: 0.82rem; color: #555; }}
.controls label {{ display: flex; align-items: center; gap: 6px; }}
.controls select {{ background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 3px 6px; font-size: 0.82rem; }}
.controls input[type="range"] {{ width: 180px; accent-color: #2a7ae2; }}
.btn {{ background: #fff; color: #2a7ae2; border: 1px solid #2a7ae2; border-radius: 4px; padding: 3px 12px; font-size: 0.82rem; cursor: pointer; }}
.btn:hover {{ background: rgba(42,122,226,0.06); }}
#canvas-wrap {{ width: 100%; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; background: #fff; }}
#canvas-wrap canvas {{ display: block; }}
p.caption {{ font-size: 0.82rem; color: #828282; font-style: italic; margin-top: 6px; font-family: "Palatino", "Palatino Linotype", Georgia, serif; }}
</style>
</head>
<body>
<div id="wrapper">
  <h2>Where Do They Build?</h2>
  <p class="desc">
    Each dot is a U.S. county colored by baseline approval probability (red = low, green = high).
    Blue circles show where data centers get built under the selected scenario. Hit play to watch a decade unfold.
  </p>
  <div class="controls">
    <label>Scenario:
      <select id="sc">
        <option value="s1">S1 &mdash; Laissez-Faire</option>
        <option value="s2">S2 &mdash; Majority (50%)</option>
        <option value="s3">S3 &mdash; Supermajority (75%)</option>
        <option value="s4" selected>S4 &mdash; Firm Consent (50%)</option>
        <option value="s5">S5 &mdash; Firm Consent (75%)</option>
      </select>
    </label>
    <label>Month: <span id="ml">Jun 2026 (6)</span>
      <input type="range" id="ms" min="12" max="120" step="12" value="12">
    </label>
    <button id="pb" class="btn">&#9654; Play</button>
  </div>
  <div id="canvas-wrap"></div>
  <p class="caption">
    3,109 continental U.S. counties &middot; 10,000 Monte Carlo draws &middot; XGBoost approval model
  </p>
</div>

<script>
// === INLINE DATA ===
const COUNTIES={counties_json};
const BUILDS={builds_json};
const TS={ts_json};

// === LOOKUP ===
const CL={{}};
COUNTIES.forEach(c=>CL[c[0]]=c);

const MN=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const SNAMES={{s1:"S1 — Laissez-Faire",s2:"S2 — Majority (50%)",s3:"S3 — Supermajority (75%)",s4:"S4 — Firm Consent (50%)",s5:"S5 — Firm Consent (75%)"}};
const SCOL={{s1:[37,99,235],s2:[124,58,237],s3:[220,38,38],s4:[22,163,74],s5:[217,119,6]}};

let scenario="s4", month=12, playing=false, ptimer=0;

function approvalColor(prob){{
  const stops=[[0,180,30,30],[.3,210,120,40],[.5,190,170,70],[.7,100,160,80],[1,30,120,55]];
  const t=Math.max(0,Math.min(1,(prob-.05)/.9));
  let lo=stops[0],hi=stops[stops.length-1];
  for(let i=0;i<stops.length-1;i++)if(t>=stops[i][0]&&t<=stops[i+1][0]){{lo=stops[i];hi=stops[i+1];break;}}
  const f=hi[0]===lo[0]?0:(t-lo[0])/(hi[0]-lo[0]);
  return[lo[1]+(hi[1]-lo[1])*f,lo[2]+(hi[2]-lo[2])*f,lo[3]+(hi[3]-lo[3])*f];
}}

const LONMIN=-125,LONMAX=-66,LATMIN=24.5,LATMAX=49.5;
const P={{t:10,r:10,b:36,l:10}};
let cW,cH;

function lonX(lon){{return P.l+((lon-LONMIN)/(LONMAX-LONMIN))*(cW-P.l-P.r);}}
function latY(lat){{return P.t+((LATMAX-lat)/(LATMAX-LATMIN))*(cH-P.t-P.b);}}

function updLabel(){{
  const yr=2026+Math.floor((month-1)/12);
  const m=(month-1)%12;
  document.getElementById("ml").textContent=MN[m]+" "+yr+" ("+month+")";
}}

const sk=(p)=>{{
  p.setup=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;
    cH=Math.max(360,Math.min(cW*.55,480));
    p.createCanvas(cW,cH).parent("canvas-wrap");
    p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    p.noLoop();
  }};
  p.draw=()=>{{
    p.background(248,248,246);
    p.noStroke();
    for(const c of COUNTIES){{
      const col=approvalColor(c[3]);
      p.fill(col[0],col[1],col[2],110);
      p.circle(lonX(c[1]),latY(c[2]),3);
    }}
    // Find closest available snapshot
    let snapKey=String(month);
    const scBuilds=BUILDS[scenario];
    let snap=scBuilds?scBuilds[snapKey]:null;
    // Fallback to nearest available month
    if(!snap){{
      const available=Object.keys(scBuilds||{{}}).map(Number).sort((a,b)=>a-b);
      const closest=available.reduce((prev,curr)=>Math.abs(curr-month)<Math.abs(prev-month)?curr:prev,available[0]||6);
      snap=scBuilds?scBuilds[String(closest)]:null;
    }}
    if(snap){{
      let mx=0;
      for(const f in snap)mx=Math.max(mx,snap[f]);
      for(const f in snap){{
        const c=CL[f];
        if(!c)continue;
        const sz=5+24*Math.sqrt(snap[f]/Math.max(mx,1));
        p.fill(37,99,235,160);
        p.stroke(37,99,235,80);
        p.strokeWeight(.5);
        p.circle(lonX(c[1]),latY(c[2]),sz);
      }}
    }}
    // Stats
    const ts=TS[scenario];
    const row=ts[Math.min(month-1,ts.length-1)];
    p.noStroke();p.fill(255,255,255,235);p.rect(cW-210,8,200,72,5);
    p.stroke(210);p.strokeWeight(.5);p.noFill();p.rect(cW-210,8,200,72,5);
    p.noStroke();p.fill(17);p.textAlign(p.LEFT,p.TOP);p.textSize(12);
    p.textStyle(p.BOLD);p.text(MN[row.cal-1]+" "+row.yr,cW-200,14);
    p.textStyle(p.NORMAL);p.textSize(10);p.fill(80);
    p.text("Built: "+row.b.toFixed(0)+" facilities",cW-200,32);
    p.text("Capacity: "+row.gw.toFixed(1)+" GW",cW-200,46);
    p.text("Gini: "+row.gi.toFixed(3),cW-200,60);
    // Legend
    p.textAlign(p.LEFT,p.CENTER);p.textSize(9);p.fill(130);p.noStroke();
    p.text("Low approval",10,cH-12);
    for(let i=0;i<70;i++){{const col=approvalColor(.05+(i/69)*.9);p.stroke(col[0],col[1],col[2]);p.line(82+i,cH-18,82+i,cH-7);}}
    p.noStroke();p.fill(130);p.text("High",156,cH-12);
    p.fill(37,99,235,160);p.noStroke();p.circle(200,cH-12,8);p.fill(130);p.text("= Facilities built",208,cH-12);
    // Play
    if(playing){{
      ptimer++;
      if(ptimer%6===0){{
        month+=12;
        if(month>120){{month=6;playing=false;document.getElementById("pb").innerHTML="&#9654; Play";}}
        document.getElementById("ms").value=month;updLabel();
      }}
      p.loop();
    }}else p.noLoop();
  }};
  p.windowResized=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(360,Math.min(cW*.55,480));
    p.resizeCanvas(cW,cH);p.redraw();
  }};
}};

const inst=new p5(sk);
document.getElementById("sc").addEventListener("change",e=>{{scenario=e.target.value;inst.redraw();}});
document.getElementById("ms").addEventListener("input",e=>{{month=parseInt(e.target.value);updLabel();inst.redraw();}});
document.getElementById("pb").addEventListener("click",()=>{{
  playing=!playing;
  document.getElementById("pb").innerHTML=playing?"&#9724; Pause":"&#9654; Play";
  if(playing){{if(month>=120)month=12;inst.loop();}}
}});
updLabel();
</script>
</body>
</html>"""

    with open(OUT, "w") as f:
        f.write(html)

    print(f"\nWrote {OUT} ({OUT.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()
