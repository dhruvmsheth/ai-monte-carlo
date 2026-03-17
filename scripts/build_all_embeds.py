#!/usr/bin/env python3
"""Generate self-contained HTML embeds for all interactive visualizations.

Outputs:
  website/embeds/growth-chart.html       — MC growth trajectories with 2025 baseline
  website/embeds/baseline-map.html       — Current 2025 datacenter snapshot
  website/embeds/scenario-snapshots.html — 2035 end-state maps (toggle scenarios)
  website/embeds/cost-benefit.html       — Surplus vs firm cost comparison
"""
import csv
import json
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parent.parent
WEBSITE_DATA = PROJECT / "website" / "data"
FEATURE_MATRIX = PROJECT / "data" / "processed" / "county_feature_matrix.csv"
GEOJSON_CACHE = PROJECT / "data" / "external" / "counties_geojson.json"
EMBED_DIR = PROJECT / "website" / "embeds"

# ── Shared data loaders ──────────────────────────────────────────────────

def load_counties_with_centroids():
    """Merge feature matrix counties with GeoJSON centroids."""
    # Centroids
    with open(GEOJSON_CACHE) as f:
        geo = json.load(f)
    centroids = {}
    for feat in geo["features"]:
        fips = feat["id"]
        coords = feat["geometry"]["coordinates"]
        pts = []
        if feat["geometry"]["type"] == "Polygon":
            for ring in coords: pts.extend(ring)
        elif feat["geometry"]["type"] == "MultiPolygon":
            for poly in coords:
                for ring in poly: pts.extend(ring)
        if pts:
            arr = np.array(pts)
            centroids[fips] = (round(float(arr[:, 0].mean()), 2),
                               round(float(arr[:, 1].mean()), 2))

    # Feature matrix
    rows = []
    with open(FEATURE_MATRIX) as f:
        reader = csv.DictReader(f)
        for r in reader:
            fips = r["fips"]
            if fips not in centroids:
                continue
            lon, lat = centroids[fips]
            if lon < -130 or lon > -60 or lat < 23 or lat > 50:
                continue
            rows.append({
                "f": fips,
                "x": lon,
                "y": lat,
                "n": r["county"],
                "st": r["state"],
                "fc": int(r["facility_count"]),
                "mw": round(float(r["total_mw"]), 0),
                "sat": int(r["saturation_count"]),
            })
    return rows


def load_all_county_centroids():
    """Load all county centroids with approval probs (for background dots)."""
    with open(WEBSITE_DATA / "counties.json") as f:
        return json.load(f)


def load_timeseries():
    with open(WEBSITE_DATA / "timeseries.json") as f:
        return json.load(f)


def load_summary():
    with open(WEBSITE_DATA / "summary.json") as f:
        return json.load(f)


def load_builds_final():
    """Load county builds at month 120 for all scenarios."""
    with open(WEBSITE_DATA / "county_builds.json") as f:
        builds = json.load(f)
    result = {}
    for sid, snaps in builds.items():
        result[sid] = snaps.get("120", {})
    return result


# ── Shared HTML helpers ──────────────────────────────────────────────────

SHARED_STYLE = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #fdfdfd; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, sans-serif; color: #111; }
#wrapper { max-width: 900px; margin: 0 auto; padding: 16px; }
h2 { font-family: "Palatino", "Palatino Linotype", Georgia, serif; font-weight: 400; font-size: 1.8rem; margin-bottom: 8px; }
p.desc { font-family: "Palatino", "Palatino Linotype", Georgia, serif; font-size: 1rem; color: #555; line-height: 1.6; margin-bottom: 12px; }
.controls { display: flex; flex-wrap: wrap; align-items: center; gap: 14px; margin-bottom: 8px; font-size: 0.82rem; color: #555; }
.controls label { display: flex; align-items: center; gap: 6px; }
.controls select, .controls input[type="checkbox"] { background: #fff; border: 1px solid #ddd; border-radius: 4px; padding: 3px 6px; font-size: 0.82rem; }
.controls input[type="range"] { width: 180px; accent-color: #2a7ae2; }
.controls input[type="checkbox"] { accent-color: #2a7ae2; }
.btn { background: #fff; color: #2a7ae2; border: 1px solid #2a7ae2; border-radius: 4px; padding: 3px 12px; font-size: 0.82rem; cursor: pointer; }
.btn:hover { background: rgba(42,122,226,0.06); }
#canvas-wrap { width: 100%; border: 1px solid #e8e8e8; border-radius: 6px; overflow: hidden; background: #fff; }
#canvas-wrap canvas { display: block; }
p.caption { font-size: 0.82rem; color: #828282; font-style: italic; margin-top: 6px; font-family: "Palatino", "Palatino Linotype", Georgia, serif; }
"""

SHARED_JS_CONSTANTS = """
const MN=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
const SIDS=["s1","s2","s3","s4","s5"];
const SNAMES={s1:"S1 — Laissez-Faire",s2:"S2 — Majority (50%)",s3:"S3 — Supermajority (75%)",s4:"S4 — Firm Consent (50%)",s5:"S5 — Firm Consent (75%)"};
const SCOL={s1:[37,99,235],s2:[124,58,237],s3:[220,38,38],s4:[22,163,74],s5:[217,119,6]};
"""


# ── Embed 1: Growth Chart ────────────────────────────────────────────────

def build_growth_chart():
    ts = load_timeseries()
    # Compact timeseries
    compact = {}
    for sid, rows in ts.items():
        compact[sid] = [
            [r["month"], r["year"], r["cal"],
             round(r["built"], 1), round(r["built_lo"], 1), round(r["built_hi"], 1),
             round(r["gw"], 1), round(r["gw_lo"], 1), round(r["gw_hi"], 1)]
            for r in rows
        ]
    ts_json = json.dumps(compact, separators=(",", ":"))

    # Baseline: existing capacity
    with open(FEATURE_MATRIX) as f:
        reader = csv.DictReader(f)
        total_mw = sum(float(r["total_mw"]) for r in reader)
    baseline_gw = round(total_mw / 1000, 1)
    # Existing facility count
    with open(FEATURE_MATRIX) as f:
        reader = csv.DictReader(f)
        total_fc = sum(int(r["facility_count"]) for r in reader)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<style>{SHARED_STYLE}</style>
</head><body>
<div id="wrapper">
  <h2>Growth Trajectories</h2>
  <p class="desc">
    Starting from today's {total_fc} existing facilities ({baseline_gw} GW), how does data center
    capacity grow over the next decade? Each scenario tells a dramatically different story.
    Shaded bands show 95% confidence intervals across 10,000 Monte Carlo simulations.
  </p>
  <div class="controls">
    <label><input type="checkbox" id="ci" checked> Show 95% CI</label>
    <label>Metric: <select id="met"><option value="gw" selected>Cumulative GW</option><option value="built">Facilities Built</option></select></label>
  </div>
  <div id="canvas-wrap"></div>
  <p class="caption">10,000 Monte Carlo draws per scenario, 120 monthly steps (Jan 2026 – Dec 2035). Baseline: {total_fc} existing facilities / {baseline_gw} GW as of 2025.</p>
</div>
<script>
{SHARED_JS_CONSTANTS}
const TS={ts_json};
const BASE_GW={baseline_gw};
const BASE_FC={total_fc};
// TS format: [month, year, cal_month, built, built_lo, built_hi, gw, gw_lo, gw_hi]

let metric="gw", showCI=true, anim=0, cW, cH;
const PAD={{t:40,r:30,b:55,l:70}};

const sk=(p)=>{{
  p.setup=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth; cH=Math.max(380,Math.min(cW*.5,480));
    p.createCanvas(cW,cH).parent("canvas-wrap");
    p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
  }};
  p.draw=()=>{{
    p.background(253);
    const pW=cW-PAD.l-PAD.r, pH=cH-PAD.t-PAD.b;
    // Indices: 0=month,1=year,2=cal,3=built,4=built_lo,5=built_hi,6=gw,7=gw_lo,8=gw_hi
    const iVal=metric==="gw"?6:3, iHi=metric==="gw"?8:5, iLo=metric==="gw"?7:4;
    const base=metric==="gw"?BASE_GW:BASE_FC;

    let yMax=base;
    for(const sid of SIDS)for(const r of TS[sid])yMax=Math.max(yMax,base+(r[iHi]||r[iVal]));
    yMax=Math.ceil(yMax*1.08);

    if(anim<1)anim=Math.min(1,anim+.01);
    const vis=Math.floor(120*anim);

    p.push(); p.translate(PAD.l,PAD.t);

    // Grid
    const nY=5;
    for(let i=0;i<=nY;i++){{
      const yy=pH-(i/nY)*pH;
      p.stroke(230);p.strokeWeight(.7);p.line(0,yy,pW,yy);
      p.noStroke();p.fill(130);p.textAlign(p.RIGHT,p.CENTER);p.textSize(10);
      const v=yMax*i/nY;
      p.text(metric==="gw"?v.toFixed(0)+" GW":v.toFixed(0),-8,yy);
    }}
    // X labels
    p.noStroke();p.fill(130);p.textAlign(p.CENTER,p.TOP);p.textSize(10);
    // 2025 label at x=0
    p.text("2025",0,pH+6);
    for(let yr=2026;yr<=2035;yr++){{
      const m=(yr-2026)*12+6;
      p.text(yr.toString(),(m/120)*pW,pH+6);
    }}
    // Y label
    p.push();p.translate(-55,pH/2);p.rotate(-p.HALF_PI);
    p.textAlign(p.CENTER,p.CENTER);p.textSize(11);p.fill(100);
    p.text(metric==="gw"?"Cumulative Capacity (GW)":"Total Facilities",0,0);
    p.pop();

    // Baseline dashed line
    const baseY=pH-(base/yMax)*pH;
    p.stroke(160);p.strokeWeight(1);
    p.drawingContext.setLineDash([4,3]);
    p.line(0,baseY,pW,baseY);
    p.drawingContext.setLineDash([]);
    p.noStroke();p.fill(130);p.textAlign(p.LEFT,p.BOTTOM);p.textSize(9);
    p.text("2025 baseline: "+(metric==="gw"?base.toFixed(0)+" GW":base+" facilities"),4,baseY-3);

    // CI + lines
    for(const sid of SIDS){{
      const ts=TS[sid], col=SCOL[sid];
      if(showCI){{
        p.fill(col[0],col[1],col[2],20);p.noStroke();p.beginShape();
        for(let i=0;i<Math.min(ts.length,vis);i++)
          p.vertex((ts[i][0]/120)*pW, pH-((base+ts[i][iHi])/yMax)*pH);
        for(let i=Math.min(ts.length,vis)-1;i>=0;i--)
          p.vertex((ts[i][0]/120)*pW, pH-((base+ts[i][iLo])/yMax)*pH);
        p.endShape(p.CLOSE);
      }}
      p.stroke(col[0],col[1],col[2]);p.strokeWeight(2);p.noFill();p.beginShape();
      for(let i=0;i<Math.min(ts.length,vis);i++)
        p.vertex((ts[i][0]/120)*pW, pH-((base+ts[i][iVal])/yMax)*pH);
      p.endShape();
    }}

    // Hover
    const mx=p.mouseX-PAD.l, my=p.mouseY-PAD.t;
    if(mx>=0&&mx<=pW&&my>=0&&my<=pH){{
      const hm=Math.max(1,Math.min(120,Math.round((mx/pW)*120)));
      const hx=(hm/120)*pW;
      p.stroke(180);p.strokeWeight(.8);p.line(hx,0,hx,pH);
      const idx=hm-1, r0=TS.s1[idx];
      const tX=hx+12>pW-155?hx-168:hx+12;
      p.noStroke();p.fill(255,255,255,248);p.rect(tX-2,6,162,22+SIDS.length*19,4);
      p.stroke(210);p.strokeWeight(.5);p.noFill();p.rect(tX-2,6,162,22+SIDS.length*19,4);
      p.noStroke();p.fill(17);p.textAlign(p.LEFT,p.TOP);p.textSize(11);
      p.textStyle(p.BOLD);p.text(MN[r0[2]-1]+" "+r0[1],tX+6,10);p.textStyle(p.NORMAL);
      for(let s=0;s<SIDS.length;s++){{
        const sid=SIDS[s],col=SCOL[sid],r=TS[sid][idx],v=base+r[iVal];
        const dy=pH-(v/yMax)*pH;
        p.fill(col[0],col[1],col[2]);p.noStroke();p.circle(hx,dy,7);
        const ty=28+s*19;
        p.fill(col[0],col[1],col[2]);p.circle(tX+10,ty+5,7);
        p.fill(60);p.textSize(10);
        p.text(sid.toUpperCase()+": "+(metric==="gw"?v.toFixed(1)+" GW":v.toFixed(0)),tX+20,ty);
      }}
    }}
    p.pop();

    // Legend
    p.textAlign(p.LEFT,p.CENTER);p.textSize(10);
    let lx=PAD.l,ly=cH-16;
    for(const sid of SIDS){{
      const col=SCOL[sid],nm=SNAMES[sid],w=p.textWidth(nm)+28;
      if(lx+w>cW-10){{lx=PAD.l;ly+=14;}}
      p.fill(col[0],col[1],col[2]);p.noStroke();p.rect(lx,ly-1,12,2.5,1);
      p.fill(100);p.text(nm,lx+16,ly);lx+=w;
    }}
    if(anim>=1)p.noLoop();
  }};
  p.mouseMoved=()=>p.loop();
  p.windowResized=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.5,480));
    p.resizeCanvas(cW,cH);p.loop();
  }};
}};

const inst=new p5(sk);
document.getElementById("met").addEventListener("change",e=>{{metric=e.target.value;anim=0;inst.loop();}});
document.getElementById("ci").addEventListener("change",e=>{{showCI=e.target.checked;inst.loop();}});
</script></body></html>"""


# ── Embed 2: Baseline Snapshot Map ────────────────────────────────────────

def build_baseline_map():
    baseline_counties = load_counties_with_centroids()
    all_counties = load_all_county_centroids()
    bc_json = json.dumps(baseline_counties, separators=(",", ":"))
    ac_json = json.dumps(all_counties, separators=(",", ":"))

    total_fc = sum(c["fc"] for c in baseline_counties)
    total_gw = round(sum(c["mw"] for c in baseline_counties) / 1000, 1)

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<style>{SHARED_STYLE}
.stat-row {{ display: flex; gap: 20px; margin-bottom: 12px; flex-wrap: wrap; }}
.stat-box {{ background: #f7f7f4; border: 1px solid #e8e8e8; border-radius: 6px; padding: 10px 16px; text-align: center; flex: 1; min-width: 120px; }}
.stat-box .num {{ font-size: 1.5rem; font-weight: 600; color: #111; }}
.stat-box .lbl {{ font-size: 0.75rem; color: #828282; }}
</style>
</head><body>
<div id="wrapper">
  <h2>The 2025 Baseline</h2>
  <p class="desc">
    Before any simulation, this is where America's large-scale data centers stand today.
    Circle size shows facility count; color shows the county's community approval probability.
    Hover over a dot for details.
  </p>
  <div class="stat-row">
    <div class="stat-box"><div class="num">{total_fc}</div><div class="lbl">Facilities (&gt;100 MW)</div></div>
    <div class="stat-box"><div class="num">{total_gw}</div><div class="lbl">Total GW</div></div>
    <div class="stat-box"><div class="num">{len(baseline_counties)}</div><div class="lbl">Counties</div></div>
    <div class="stat-box"><div class="num">64</div><div class="lbl">With Existing DCs</div></div>
  </div>
  <div id="canvas-wrap"></div>
  <p class="caption">Source: FracTracker National Data Centers Database (July 2025). Hyperscale and mega-campus facilities (&gt;100 MW).</p>
</div>
<script>
const AC={ac_json};
const BC={bc_json};
// BC: [{{f,x,y,n,st,fc,mw,sat}}]

const LONMIN=-125,LONMAX=-66,LATMIN=24.5,LATMAX=49.5;
const P={{t:10,r:10,b:36,l:10}};
let cW,cH,hover=null;

function aColor(prob){{
  const stops=[[0,180,30,30],[.3,210,120,40],[.5,190,170,70],[.7,100,160,80],[1,30,120,55]];
  const t=Math.max(0,Math.min(1,(prob-.05)/.9));
  let lo=stops[0],hi=stops[stops.length-1];
  for(let i=0;i<stops.length-1;i++)if(t>=stops[i][0]&&t<=stops[i+1][0]){{lo=stops[i];hi=stops[i+1];break;}}
  const f=hi[0]===lo[0]?0:(t-lo[0])/(hi[0]-lo[0]);
  return[lo[1]+(hi[1]-lo[1])*f,lo[2]+(hi[2]-lo[2])*f,lo[3]+(hi[3]-lo[3])*f];
}}
function lx(lon){{return P.l+((lon-LONMIN)/(LONMAX-LONMIN))*(cW-P.l-P.r);}}
function ly(lat){{return P.t+((LATMAX-lat)/(LATMAX-LATMIN))*(cH-P.t-P.b);}}

const sk=(p)=>{{
  p.setup=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.55,500));
    p.createCanvas(cW,cH).parent("canvas-wrap");
    p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
  }};
  p.draw=()=>{{
    p.background(248,248,246);
    // Background: all 3109 counties
    p.noStroke();
    for(const c of AC){{
      const col=aColor(c.p);
      p.fill(col[0],col[1],col[2],60);
      p.circle(lx(c.x),ly(c.y),2.5);
    }}
    // Foreground: 232 FracTracker counties
    hover=null;
    const mx=p.mouseX,my=p.mouseY;
    for(const c of BC){{
      const cx=lx(c.x),cy=ly(c.y);
      const col=aColor(AC.find(a=>a.f===c.f)?.p||.44);
      const sz=c.fc>0?8+Math.sqrt(c.fc)*6:5;
      p.fill(col[0],col[1],col[2],200);
      p.stroke(50,50,50,60);p.strokeWeight(.5);
      p.circle(cx,cy,sz);
      if(p.dist(mx,my,cx,cy)<sz/2+4)hover=c;
    }}
    // Tooltip
    if(hover){{
      const tx=lx(hover.x)+15,ty=ly(hover.y)-10;
      const tw=180,th=70;
      const ax=tx+tw>cW?tx-tw-20:tx;
      p.noStroke();p.fill(255,255,255,245);p.rect(ax,ty,tw,th,5);
      p.stroke(200);p.strokeWeight(.5);p.noFill();p.rect(ax,ty,tw,th,5);
      p.noStroke();p.fill(17);p.textAlign(p.LEFT,p.TOP);
      p.textSize(11);p.textStyle(p.BOLD);
      p.text(hover.n+", "+hover.st,ax+8,ty+6);
      p.textStyle(p.NORMAL);p.textSize(10);p.fill(80);
      p.text("Facilities: "+hover.fc,ax+8,ty+24);
      p.text("Capacity: "+(hover.mw/1000).toFixed(1)+" GW",ax+8,ty+38);
      p.text("Saturation count: "+hover.sat,ax+8,ty+52);
    }}
    // Legend
    p.textAlign(p.LEFT,p.CENTER);p.textSize(9);p.fill(130);p.noStroke();
    p.text("Low approval",10,cH-12);
    for(let i=0;i<70;i++){{const col=aColor(.05+(i/69)*.9);p.stroke(col[0],col[1],col[2]);p.line(82+i,cH-18,82+i,cH-7);}}
    p.noStroke();p.fill(130);p.text("High",156,cH-12);
    p.text("Circle size = facility count",200,cH-12);
  }};
  p.mouseMoved=()=>p.loop();
  p.windowResized=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.55,500));
    p.resizeCanvas(cW,cH);p.redraw();
  }};
}};
new p5(sk);
</script></body></html>"""


# ── Embed 3: Scenario Snapshot Maps ──────────────────────────────────────

def build_scenario_snapshots():
    all_counties = load_all_county_centroids()
    baseline_counties = load_counties_with_centroids()
    builds_final = load_builds_final()

    ac_json = json.dumps(all_counties, separators=(",", ":"))
    # Compact baseline: just fips -> {x, y, fc}
    bc_compact = {c["f"]: [c["x"], c["y"], c["fc"]] for c in baseline_counties}
    bc_json = json.dumps(bc_compact, separators=(",", ":"))
    # Compact builds: only counties with > 0.5 mean builds
    builds_compact = {}
    for sid, data in builds_final.items():
        builds_compact[sid] = {
            f: round(v, 1) for f, v in data.items() if v >= 0.3
        }
    bf_json = json.dumps(builds_compact, separators=(",", ":"))

    # Lookup for centroids
    cl_json = json.dumps(
        {c["f"]: [c["x"], c["y"]] for c in all_counties
         if -130 < c["x"] < -60 and 23 < c["y"] < 50},
        separators=(",", ":")
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<style>{SHARED_STYLE}
.toggle-row {{ display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }}
.toggle-btn {{ padding: 6px 14px; border-radius: 4px; border: 1px solid #ddd; background: #fff; cursor: pointer; font-size: 0.82rem; transition: all .2s; }}
.toggle-btn.active {{ color: #fff; border-color: transparent; }}
.toggle-btn[data-s="s1"].active {{ background: rgb(37,99,235); }}
.toggle-btn[data-s="s2"].active {{ background: rgb(124,58,237); }}
.toggle-btn[data-s="s3"].active {{ background: rgb(220,38,38); }}
.toggle-btn[data-s="s4"].active {{ background: rgb(22,163,74); }}
.toggle-btn[data-s="s5"].active {{ background: rgb(217,119,6); }}
</style>
</head><body>
<div id="wrapper">
  <h2>2035: What Would the Map Look Like?</h2>
  <p class="desc">
    After a decade under each consent regime, where do data centers end up?
    Dark outlines show existing 2025 facilities; colored circles show new builds.
    Toggle between scenarios to see how consent requirements reshape the landscape.
  </p>
  <div class="toggle-row">
    <button class="toggle-btn active" data-s="s1">S1 Laissez-Faire</button>
    <button class="toggle-btn" data-s="s2">S2 Majority</button>
    <button class="toggle-btn" data-s="s3">S3 Supermajority</button>
    <button class="toggle-btn" data-s="s4">S4 Firm 50%</button>
    <button class="toggle-btn" data-s="s5">S5 Firm 75%</button>
  </div>
  <div id="canvas-wrap"></div>
  <p class="caption">Mean county-level builds across 10,000 Monte Carlo draws at month 120 (Dec 2035). Existing facilities shown as dark outlines.</p>
</div>
<script>
{SHARED_JS_CONSTANTS}
const AC={ac_json};
const BC={bc_json};
const BF={bf_json};
const CL={cl_json};

const LONMIN=-125,LONMAX=-66,LATMIN=24.5,LATMAX=49.5;
const P={{t:10,r:10,b:36,l:10}};
let cW,cH,scenario="s1";

function aColor(prob){{
  const stops=[[0,180,30,30],[.3,210,120,40],[.5,190,170,70],[.7,100,160,80],[1,30,120,55]];
  const t=Math.max(0,Math.min(1,(prob-.05)/.9));
  let lo=stops[0],hi=stops[stops.length-1];
  for(let i=0;i<stops.length-1;i++)if(t>=stops[i][0]&&t<=stops[i+1][0]){{lo=stops[i];hi=stops[i+1];break;}}
  const f=hi[0]===lo[0]?0:(t-lo[0])/(hi[0]-lo[0]);
  return[lo[1]+(hi[1]-lo[1])*f,lo[2]+(hi[2]-lo[2])*f,lo[3]+(hi[3]-lo[3])*f];
}}
function lx(lon){{return P.l+((lon-LONMIN)/(LONMAX-LONMIN))*(cW-P.l-P.r);}}
function ly(lat){{return P.t+((LATMAX-lat)/(LATMAX-LATMIN))*(cH-P.t-P.b);}}

const sk=(p)=>{{
  p.setup=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.55,500));
    p.createCanvas(cW,cH).parent("canvas-wrap");
    p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
    p.noLoop();
  }};
  p.draw=()=>{{
    p.background(248,248,246);
    const col=SCOL[scenario];
    // Background dots
    p.noStroke();
    for(const c of AC){{
      const cl=aColor(c.p);
      p.fill(cl[0],cl[1],cl[2],60);
      p.circle(lx(c.x),ly(c.y),2.5);
    }}
    // New builds (colored)
    const snap=BF[scenario]||{{}};
    let maxB=0;
    for(const f in snap)maxB=Math.max(maxB,snap[f]);
    for(const f in snap){{
      const c=CL[f];
      if(!c)continue;
      const sz=5+22*Math.sqrt(snap[f]/Math.max(maxB,1));
      p.fill(col[0],col[1],col[2],150);
      p.stroke(col[0],col[1],col[2],60);
      p.strokeWeight(.5);
      p.circle(lx(c[0]),ly(c[1]),sz);
    }}
    // Existing facilities (dark outlines)
    for(const f in BC){{
      const c=BC[f]; // [x, y, fc]
      if(c[2]===0)continue;
      const sz=5+Math.sqrt(c[2])*4;
      p.noFill();
      p.stroke(40,40,40,180);p.strokeWeight(1.5);
      p.circle(lx(c[0]),ly(c[1]),sz);
    }}
    // Stats
    let totalNew=0;for(const f in snap)totalNew+=snap[f];
    p.noStroke();p.fill(255,255,255,235);p.rect(cW-215,8,205,52,5);
    p.stroke(210);p.strokeWeight(.5);p.noFill();p.rect(cW-215,8,205,52,5);
    p.noStroke();p.fill(17);p.textAlign(p.LEFT,p.TOP);
    p.textSize(12);p.textStyle(p.BOLD);p.text(SNAMES[scenario],cW-205,14);
    p.textStyle(p.NORMAL);p.textSize(10);p.fill(80);
    p.text("New facilities by 2035: ~"+Math.round(totalNew),cW-205,34);
    p.text("Counties reached: "+Object.keys(snap).length,cW-205,48);
    // Legend
    p.textAlign(p.LEFT,p.CENTER);p.textSize(9);p.fill(130);p.noStroke();
    p.fill(col[0],col[1],col[2],150);p.circle(14,cH-12,8);
    p.fill(130);p.text("= New builds (2026–2035)",24,cH-12);
    p.noFill();p.stroke(40,40,40,180);p.strokeWeight(1.5);p.circle(180,cH-12,8);
    p.noStroke();p.fill(130);p.text("= Existing (2025)",190,cH-12);
  }};
  p.windowResized=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.55,500));
    p.resizeCanvas(cW,cH);p.redraw();
  }};
}};

const inst=new p5(sk);
document.querySelectorAll(".toggle-btn").forEach(btn=>{{
  btn.addEventListener("click",()=>{{
    document.querySelectorAll(".toggle-btn").forEach(b=>b.classList.remove("active"));
    btn.classList.add("active");
    scenario=btn.dataset.s;
    inst.redraw();
  }});
}});
</script></body></html>"""


# ── Embed 4: Cost-Benefit ─────────────────────────────────────────────────

def build_cost_benefit():
    summary = load_summary()
    # Extract just what we need
    data = {}
    for sid in ["s1", "s2", "s3", "s4", "s5"]:
        d = summary[sid]
        data[sid] = {
            "built": round(d["total_built"]["mean"]),
            "gw": round(d["cumulative_gw"]["mean"], 1),
            "surplus": round(d["community_surplus_m"]["mean"]),
            "cost": round(d["firm_cost_m"]["mean"]),
            "gini": round(d["gini_coefficient"]["mean"], 4),
            "rejected": round(d["total_rejected"]["mean"]),
        }
    data_json = json.dumps(data, separators=(",", ":"))

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<script src="https://cdnjs.cloudflare.com/ajax/libs/p5.js/1.9.4/p5.min.js"></script>
<style>{SHARED_STYLE}</style>
</head><body>
<div id="wrapper">
  <h2>The Cost of Consent</h2>
  <p class="desc">
    When firms invest in community consent, they generate economic surplus that dwarfs their costs.
    The question isn't whether consent is affordable &mdash; it's why we don't already require it.
  </p>
  <div id="canvas-wrap"></div>
  <p class="caption">Community surplus = tax revenue + employment value ($M cumulative). Firm cost = consent investment ($M cumulative). 10,000 MC draws.</p>
</div>
<script>
{SHARED_JS_CONSTANTS}
const D={data_json};

let anim=0,cW,cH,hover=-1;
const PAD={{t:45,r:30,b:70,l:75}};

const sk=(p)=>{{
  p.setup=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.5,450));
    p.createCanvas(cW,cH).parent("canvas-wrap");
    p.textFont("-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, sans-serif");
  }};
  p.draw=()=>{{
    p.background(253);
    anim=Math.min(1,anim+.015);
    const pW=cW-PAD.l-PAD.r, pH=cH-PAD.t-PAD.b;
    const sVals=[],cVals=[];
    for(const sid of SIDS){{sVals.push(D[sid].surplus/1e6);cVals.push(D[sid].cost/1e3);}}
    const maxS=Math.max(...sVals)*1.15;

    p.push();p.translate(PAD.l,PAD.t);
    // Title
    p.noStroke();p.fill(17);p.textAlign(p.CENTER,p.BOTTOM);p.textSize(12);
    p.textStyle(p.BOLD);p.text("Community Surplus vs. Firm Cost",pW/2,-10);p.textStyle(p.NORMAL);
    // Y grid
    for(let i=0;i<=5;i++){{
      const yy=pH-(i/5)*pH;
      p.stroke(230);p.strokeWeight(.7);p.line(0,yy,pW,yy);
      p.noStroke();p.fill(130);p.textAlign(p.RIGHT,p.CENTER);p.textSize(10);
      p.text("$"+(maxS*i/5).toFixed(1)+"T",-8,yy);
    }}
    p.push();p.translate(-58,pH/2);p.rotate(-p.HALF_PI);
    p.fill(100);p.textAlign(p.CENTER,p.CENTER);p.textSize(11);
    p.text("Community Surplus ($T)",0,0);p.pop();

    const gW=pW/SIDS.length, bW=gW*.5;
    hover=-1;
    for(let s=0;s<SIDS.length;s++){{
      const sid=SIDS[s],col=SCOL[sid],cx=s*gW+gW/2;
      const surplus=sVals[s],cost=cVals[s];
      const bH=(surplus/maxS)*pH*anim;
      // Bar
      p.noStroke();p.fill(col[0],col[1],col[2],180);
      p.rect(cx-bW/2,pH-bH,bW,bH,3,3,0,0);
      // Value
      p.fill(col[0],col[1],col[2]);p.textAlign(p.CENTER,p.BOTTOM);p.textSize(11);
      p.textStyle(p.BOLD);p.text("$"+surplus.toFixed(1)+"T",cx,pH-bH-3);p.textStyle(p.NORMAL);
      // Cost overlay
      if(cost>0){{
        const cH2=(cost/1000/maxS)*pH*anim;
        p.fill(220,50,50,120);p.rect(cx-bW/2,pH-cH2,bW,cH2);
        p.fill(180,40,40);p.textAlign(p.CENTER,p.TOP);p.textSize(9);
        p.text("Cost: $"+cost.toFixed(1)+"B",cx,pH+26);
      }}
      p.fill(col[0],col[1],col[2]);p.textAlign(p.CENTER,p.TOP);p.textSize(10);
      p.text(sid.toUpperCase(),cx,pH+6);
      p.fill(130);p.textSize(8);
      const short=SNAMES[sid].split("—")[1]?.trim()||sid;
      p.text(short,cx,pH+40);
      // Hover detect
      if(p.mouseX-PAD.l>cx-gW/2&&p.mouseX-PAD.l<cx+gW/2&&p.mouseY-PAD.t>0&&p.mouseY-PAD.t<pH)hover=s;
    }}
    // ROI for S4
    if(cVals[3]>0&&anim>.5){{
      const roi=Math.round(sVals[3]*1000/cVals[3]);
      const cx4=3*gW+gW/2;
      p.fill(22,163,74);p.textAlign(p.CENTER,p.BOTTOM);p.textSize(11);
      p.textStyle(p.BOLD);p.text(roi+":1 return",cx4,pH-(sVals[3]/maxS)*pH*anim-18);
      p.textStyle(p.NORMAL);
    }}
    // Hover tooltip
    if(hover>=0){{
      const sid=SIDS[hover],d=D[sid];
      const tx=p.mouseX-PAD.l+15,ty=20;
      const tw=170,th=82;
      const ax=tx+tw>pW?tx-tw-20:tx;
      p.noStroke();p.fill(255,255,255,248);p.rect(ax,ty,tw,th,4);
      p.stroke(210);p.strokeWeight(.5);p.noFill();p.rect(ax,ty,tw,th,4);
      p.noStroke();p.fill(17);p.textAlign(p.LEFT,p.TOP);p.textSize(10);
      p.textStyle(p.BOLD);p.text(SNAMES[sid],ax+8,ty+6);p.textStyle(p.NORMAL);
      p.fill(80);p.textSize(9);
      p.text("Built: "+d.built+" facilities ("+d.gw+" GW)",ax+8,ty+24);
      p.text("Surplus: $"+(d.surplus/1e6).toFixed(2)+"T",ax+8,ty+38);
      p.text("Firm cost: $"+(d.cost/1e3).toFixed(1)+"B",ax+8,ty+52);
      p.text("Gini: "+d.gini+"  |  Rejected: "+d.rejected,ax+8,ty+66);
    }}
    p.pop();
    if(anim>=1&&hover<0)p.noLoop();
  }};
  p.mouseMoved=()=>p.loop();
  p.windowResized=()=>{{
    const el=document.getElementById("canvas-wrap");
    cW=el.clientWidth;cH=Math.max(380,Math.min(cW*.5,450));
    p.resizeCanvas(cW,cH);p.loop();
  }};
}};
new p5(sk);
</script></body></html>"""


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    EMBED_DIR.mkdir(parents=True, exist_ok=True)

    embeds = [
        ("growth-chart.html", build_growth_chart),
        ("baseline-map.html", build_baseline_map),
        ("scenario-snapshots.html", build_scenario_snapshots),
        ("cost-benefit.html", build_cost_benefit),
    ]

    for name, builder in embeds:
        print(f"Building {name}...")
        html = builder()
        path = EMBED_DIR / name
        with open(path, "w") as f:
            f.write(html)
        print(f"  -> {path.name} ({path.stat().st_size // 1024}KB)")

    print(f"\nAll embeds written to {EMBED_DIR}/")


if __name__ == "__main__":
    main()
