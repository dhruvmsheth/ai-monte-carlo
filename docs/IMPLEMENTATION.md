# Implementation Guide: Data Collection, Pipeline, and Execution Plan

This document provides detailed, step-by-step guidance for implementing the data center consent simulation. It covers every data source, how to acquire and clean it, how each piece fits into the pipeline, and what research informs each decision.

---

## Table of Contents

1. [Data Architecture Overview](#1-data-architecture-overview)
2. [Dataset 1: FracTracker Core Facility Data](#2-dataset-1-fractracker-core-facility-data)
3. [Dataset 2: Opposition / Rejection Data](#3-dataset-2-opposition--rejection-data)
4. [Dataset 3: County-Level Feature Matrix](#4-dataset-3-county-level-feature-matrix)
5. [Dataset 4: Growth Projections (Candidate Queue)](#5-dataset-4-growth-projections-candidate-queue)
6. [Dataset 5: Calibration Anchors](#6-dataset-5-calibration-anchors)
7. [County FIPS Mapping Pipeline](#7-county-fips-mapping-pipeline)
8. [Data Pipeline Execution Order](#8-data-pipeline-execution-order)
9. [Simulation Implementation Details](#9-simulation-implementation-details)
10. [Visualization Plan](#10-visualization-plan)
11. [Known Risks and Mitigations](#11-known-risks-and-mitigations)

---

## 1. Data Architecture Overview

All data flows through a county-level aggregation keyed by 5-digit FIPS codes.

```
Raw Sources                    County Aggregation          Model Input
─────────────                  ──────────────────          ───────────
FracTracker CSV ──┐
                  ├─→ FIPS mapping ─→ county_features.csv ─→ XGBoost/Logistic
Opposition DBs ──┘                          │                     │
WRI Aqueduct ────────────────────────────→  │              calibrated p_county
MIT Election Lab ────────────────────────→  │                     │
Census QWI ──────────────────────────────→  │              Beta(α, β) per county
Good Jobs First ─────────────────────────→  │                     │
                                            │              Monte Carlo Engine
Growth Projections ──────────────────────────────────────→ candidate_queue
```

**Critical principle:** Every data source must be mapped to 5-digit FIPS codes. The FracTracker CSV has county names + state abbreviations but NO FIPS codes. We must add them.

---

## 2. Dataset 1: FracTracker Core Facility Data

### Source
- **File:** `Data_Centers_Database - FracTracker Data Centers.csv` (already downloaded)
- **Origin:** FracTracker National Data Centers Tracker, July 2025
- **Google Sheet:** https://docs.google.com/spreadsheets/d/1JJ6kcVo-NjlAYtznwHOki2DVl4WWV6lhy-eXhFCdKKU/

### Raw Data Profile (1,380 rows, 43 columns)

| Column | Description | Coverage |
|--------|-------------|----------|
| `facility_name` | Name of facility/project | 100% |
| `state`, `county`, `city` | Location | county: 100%, all have lat/long |
| `lat`, `long` | Coordinates | 100% (1,380/1,380) |
| `status` | Operating/Proposed/Approved/Suspended/Cancelled/Expanding/Unknown | 100% |
| `mw` | Capacity in MW | 31% (432/1,380) — many "Unknown" |
| `sizerank` | Size tier (Small/Medium/Large/Hyperscale/Mega/Unknown) | 40% known, 60% "Unknown" |
| `operator_name` | Developer/operator | partial |
| `tenant` | End customer (Google, AWS, etc.) | sparse |
| `cooling_type` | Closed loop/Open loop/Fans | 2% (mostly empty) |
| `community_pushback` | "Yes" / empty | 12% have pushback (163 facilities) |
| `resistance_status` | Descriptive text (moratorium details, etc.) | <1% |
| `power_source` | Grid/Natural gas/Solar/Nuclear/etc. | 4% |
| `project_cost` | Dollar amount | sparse |

### Status Distribution
| Status | Count |
|--------|-------|
| Proposed | 579 |
| Operating | 492 |
| Approved/Permitted/Under construction | 105 |
| Unknown | 77 |
| Suspended | 53 |
| Expanding | 50 |
| Cancelled | 24 |

### Size Distribution
| Size Rank | Count | Use in Model |
|-----------|-------|-------------|
| Mega campus (>1,000 MW) | 76 | **Core** |
| Hyperscale (100-999 MW) | 261 | **Core** |
| Large (51-99 MW) | 26 | Exclude (below 100MW threshold) |
| Medium (11-50 MW) | 97 | Exclude |
| Small (0-10 MW) | 91 | Exclude |
| Unknown | 829 | **Include Virginia Operating** for saturation counts |

### Filtering Strategy

**Core modeling set: Hyperscale + Mega campus = 337 facilities across 235 counties**

However, the 829 "Unknown" entries are critical for Virginia saturation counts:
- 412 of 829 Unknown are in Virginia
- 308 Unknown are "Operating" (mostly Loudoun County)
- Loudoun County alone has 98 Operating/Unknown entries — these are real facilities that predate the >100MW size tracking

**Two-tier approach:**
1. **Tier 1 (model training):** 337 Hyperscale/Mega facilities — used for county-level feature matrix and binary outcome coding
2. **Tier 2 (saturation counts):** All Operating facilities regardless of size — used for computing county saturation count `n` which drives the intervention functions

This is because saturation effects (community fatigue) depend on how many total DCs are in a county, not just the large ones.

### Top States (>100MW only)
TX: 57, GA: 49, PA: 27, VA: 24, AZ: 16, NY: 14, IN: 12, MI: 12, OH: 10

### Top Counties (>100MW only)
Bexar TX: 13, Maricopa AZ: 12, Douglas GA: 9, Ellis TX: 9, Fulton GA: 8

### County-Level Outcome Coding
After aggregating to county level (>100MW facilities):
- **77 counties** coded as "approved" (majority of facilities operating/permitted)
- **31 counties** coded as "blocked" (majority suspended/cancelled)
- **127 counties** with only proposed projects (no outcome yet — exclude from training, but include for prediction)

**Training set: ~108 counties with a known outcome (77 approved + 31 blocked)**

This is larger than the proposal's estimate of 60-80, which is good for model reliability.

### Implementation: `src/data/ingest.py`

```python
def load_fractracker(path: str) -> pd.DataFrame:
    """Load and clean FracTracker CSV.

    Steps:
    1. Read CSV, strip whitespace from all string columns
    2. Parse MW: handle commas, '>' prefix, convert to float (NaN if missing)
    3. Normalize status values (strip trailing spaces)
    4. Normalize community_pushback to boolean
    5. Add FIPS codes via county+state lookup (see Section 7)
    6. Filter to Tier 1 (Hyperscale + Mega) for modeling
    7. Compute Tier 2 saturation counts (all Operating facilities)
    """
```

```python
def aggregate_to_county(facilities: pd.DataFrame) -> pd.DataFrame:
    """Aggregate facility-level data to county level.

    Per county, compute:
    - facility_count: total >100MW facilities
    - total_mw: sum of MW (where available)
    - saturation_count: count of ALL operating facilities (Tier 2)
    - pushback_flag: 1 if any facility has community_pushback=Yes
    - share_opposed: fraction of facilities that are suspended/cancelled
    - hyperscaler_share: fraction where operator is Microsoft/Amazon/Google/Meta
    - avg_project_mw: mean MW of facilities with known MW
    - cooling_water_intensive: 1 if mode of cooling_type includes water
    - binary_outcome: 1 if majority approved, 0 if majority blocked
    """
```

---

## 3. Dataset 2: Opposition / Rejection Data

### 3a. Data Center Watch

- **Source:** https://www.datacenterwatch.org/database
- **Format:** Interactive web database, exportable to CSV/XLSX
- **Coverage:** ~20 major blocked/delayed projects per quarter, total ~$162B tracked since 2023
- **Fields:** Project Name, Location (City/State), Estimated Investment, Nature of Opposition, Status
- **FIPS codes:** No — locations given as City/State, need mapping

**Acquisition:** Check if CSV export is available from the database page. If not, manual extraction from their quarterly reports. The key data we need is which counties have blocked/delayed projects.

### 3b. Robert Bryce Rejection Database

- **Source:** Robert Bryce's Substack (robertbryce.substack.com)
- **Format:** Tables embedded in articles (NOT a standalone spreadsheet)
- **Latest update:** February 25, 2026, "Europe To Big Tech: We Don't Want You, Either"
- **Coverage:** 39+ U.S. cases of moratoria, bans, or restrictive ordinances since January 2023
- **Fields:** Date, Location (State + Government body), Entity/Developer, Type (Moratorium/Ban/Ordinance), Summary, Source links
- **FIPS codes:** No — but the "Government" field often names the county directly

**Acquisition:** Manual extraction from Substack articles into a CSV. This is ~40 rows of data — an hour of work. Create `data/external/bryce_rejections.csv` with columns: `date, state, county, entity, type, summary, source_url`.

### Merging Opposition Data with FracTracker

The FracTracker CSV already has `community_pushback` and `resistance_status` fields. The opposition datasets supplement this:

1. Start with FracTracker's `community_pushback = "Yes"` (163 facilities, ~100 counties)
2. Cross-reference with Bryce's 39 cases — add any counties not already flagged
3. Cross-reference with Data Center Watch — same process
4. Result: a comprehensive `pushback_flag` per county (binary: ever had organized opposition)

**Important:** There will be overlap. Many of the Bryce cases (Prince William VA, Culpeper VA, etc.) already appear in FracTracker's pushback column. The merge is additive — we only add new counties, never remove existing flags.

### Implementation: `src/data/ingest.py`

```python
def load_opposition_data() -> pd.DataFrame:
    """Load and merge opposition datasets.

    Returns DataFrame with columns: fips, county, state, opposition_type, source
    Sources: FracTracker pushback field + Bryce CSV + Data Center Watch CSV
    """
```

---

## 4. Dataset 3: County-Level Feature Matrix

This is the most complex data collection task. We need 10 features per county, from 6 different sources.

### 4a. Saturation Count / Total MW

- **Source:** FracTracker (already loaded)
- **Implementation:** Direct computation from `aggregate_to_county()` — see Section 2

### 4b. Water Stress Decile

- **Source:** WRI Aqueduct Water Risk Atlas 4.0
- **GitHub:** https://github.com/wri/Aqueduct40
- **Data dictionary:** https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md
- **Format:** GeoPackage (.gpkg) or shapefile with water stress scores per watershed
- **Resolution:** Watershed/basin level (NOT county level) — requires spatial join

**Approach — two options:**

**Option A (Recommended): Point-in-polygon using county centroids**
1. Download Aqueduct 4.0 global maps from WRI data page
2. For each county in our dataset, use the county centroid lat/long (available from Census TIGER files or computed from FracTracker facility coordinates)
3. Spatial join: find which Aqueduct watershed polygon contains each county centroid
4. Extract `bws_cat` (baseline water stress category, 1-5 scale) or `bws_raw` (continuous 0-5)
5. Discretize to deciles across our county set

**Option B (Simpler): Use FracTracker lat/long as proxy**
1. For each county, take the mean lat/long of facilities in that county (from FracTracker)
2. Use the WRI Aqueduct online tool's "location upload" feature to batch-query water stress for those coordinates
3. Export results as CSV

**Option C (Simplest): Pre-computed county water stress dataset**
Search for existing county-level water stress datasets derived from Aqueduct. Several academic papers have published these. If found, use directly.

**Python libraries needed:** `geopandas` for spatial join (Option A), or `requests` for API calls (Option B).

**Implementation:** `src/data/features.py`

```python
def get_water_stress(county_centroids: pd.DataFrame) -> pd.Series:
    """Get water stress decile for each county.

    county_centroids: DataFrame with fips, lat, long
    Returns: Series indexed by fips with water stress decile (1-10)
    """
```

### 4c. DC Employment / Growth (2020-2025)

- **Source:** Census Bureau Quarterly Workforce Indicators (QWI)
- **API endpoint:** `https://api.census.gov/data/timeseries/qwi/sa`
- **NAICS code:** 518210 (Data Processing, Hosting and Related Services)
- **Requires:** Free Census API key (https://api.census.gov/data/key_signup.html)
- **Available data:** Employment (Emp), hires (HirA), separations (Sep), earnings

**API call pattern:**
```
GET https://api.census.gov/data/timeseries/qwi/sa
  ?get=Emp
  &for=county:*
  &in=state:{state_fips}
  &year=2020,2021,2022,2023,2024,2025
  &quarter=1,2,3,4
  &ownercode=A05        (private sector)
  &seasonadj=U          (unadjusted)
  &industry=518210
  &key={API_KEY}
```

**Gotchas:**
- Must query one state at a time (the API requires `in=state:XX`)
- Many counties will return no data for NAICS 518210 — assign 0, not NaN
- Some state-quarter combos may be suppressed for confidentiality
- Latest available quarter likely R2025Q2 (released ~6 months after reference period)
- Rate limit: ~500 requests/day without key, unlimited with key

**Implementation:** `src/data/qwi.py`

```python
def fetch_qwi_employment(
    state_fips_list: list[str],
    api_key: str,
    naics: str = "518210",
    years: list[int] = [2020, 2021, 2022, 2023, 2024, 2025],
) -> pd.DataFrame:
    """Fetch county-level employment from Census QWI API.

    Returns DataFrame: fips, year, quarter, employment
    Counties not found get 0.

    Loops over states because the API requires state-level queries.
    Caches raw API responses to data/raw/qwi/ for reproducibility.
    """
```

**Derived features:**
- `dc_employment`: Latest available quarter's employment count
- `dc_employment_growth`: 5-year growth rate (2020 → 2025)

### 4d. Partisan Lean (% Republican 2024)

- **Source:** MIT Election Lab, County Presidential Election Returns 2000-2024
- **Download:** https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VOQCHQ
- **Alternative:** https://github.com/tonmcg/US_County_Level_Election_Results_08-24
- **Format:** CSV/TSV with FIPS codes included
- **Key columns:** `county_fips`, `party`, `candidatevotes`, `totalvotes`

**Implementation:**

```python
def get_partisan_lean(election_csv_path: str) -> pd.Series:
    """Compute % Republican vote share per county from 2024 presidential returns.

    Returns Series indexed by fips with float 0.0-1.0.
    If 2024 isn't available yet, fall back to 2020.
    """
```

**Note:** The MIT Election Lab dataset includes FIPS codes natively — no mapping needed. This is one of the cleanest data sources.

### 4e. Pushback Flag

- **Source:** FracTracker `community_pushback` + opposition datasets (Section 3)
- **Binary:** 1 if county has ever had organized opposition to any DC, 0 otherwise
- **Already computed** during opposition data merge

### 4f. State Incentive Generosity

- **Source:** Good Jobs First, "Cloudy Data, Costly Deals" (November 2025)
- **URL:** https://goodjobsfirst.org/cloudy-data-costly-deals-how-poorly-states-disclose-data-center-subsidies/
- **Format:** This is a **report**, not a downloadable dataset. We must manually extract state-level scores.
- **Supplementary:** Consumer Energy Alliance Florida report ($405.8M/GW annual tax revenue per GW)

**Approach:**
1. Read the Good Jobs First report — extract their state-by-state transparency/generosity rankings
2. Create a manual `data/external/state_incentives.csv` with columns: `state, incentive_score, source_notes`
3. Scale to 0-1 where 1 = most generous incentives
4. Apply uniformly to all counties in each state (as proposed)

**Alternative if GJF doesn't have a clean ranking:** Use a simpler proxy:
- States with explicit DC tax exemptions (Virginia, Georgia, Texas, Ohio, etc.) get high score
- States with moratoriums or restrictions get low score
- States with no specific policy get middle score

### 4g. Project MW (County Average)

- **Source:** FracTracker MW column
- **Implementation:** Mean MW of >100MW facilities per county (from Tier 1 data)
- **Note:** 69% of facilities have missing MW. For counties where no facility has MW data, use the median of known values (~200 MW)

### 4h. Cooling Water-Intensive Flag

- **Source:** FracTracker `cooling_type` column
- **Problem:** Only 2% of facilities have cooling_type data (29 of 1,380)
- **This feature may not be usable.** Consider dropping it or using a proxy.
- **Proxy option:** Use water_stress_decile as a combined water concern metric instead

### 4i. Hyperscaler Operator Share

- **Source:** FracTracker `operator_name` column
- **Implementation:** For each county, compute fraction of facilities where operator is Microsoft, Amazon, Google, or Meta
- **Hyperscaler list:** Microsoft, Amazon (including "Amazon Data Services Inc"), Google, Meta, Apple, Oracle
- **String matching needed** — operators have variant names

### 4j. Baseline Monthly Additions (State-Prorated)

- **Source:** Growth projections (see Section 5)
- **Implementation:** State-level allocation from national monthly GW rate

---

## 5. Dataset 4: Growth Projections (Candidate Queue)

### Source Figures

| Source | Figure | Derivation |
|--------|--------|-----------|
| JLL 2026 Outlook | 97 GW global 2025-2030 | U.S. at 80-90% → 78-87 GW over 5 years → 1.3-1.5 GW/month |
| ABI Research | 10.2 → 71.8 GW U.S. 2025-2035 | 61.6 GW over 10 years → 0.5 GW/month (includes efficiency gains) |
| Cushman & Wakefield | 25.3 GW under construction end-2025 | Near-term pipeline anchor |

### Reconciliation

The JLL and ABI figures measure different things:
- **JLL:** Provisioned facility power (includes cooling, redundancy) — overestimates actual demand
- **ABI:** Active IT critical load — more conservative but closer to real grid impact

**Recommended approach:** Use a time-varying rate:
- **2026-2030:** 1.4 GW/month (aggressive AI buildout phase, consistent with JLL)
- **2031-2035:** 0.8 GW/month (grid constraints, inference optimization slows growth)

For simplicity in Phase 1, use a constant **1.5 GW/month** (the config default). The time-varying rate can be a Phase 3 sensitivity variant.

### State-Level Distribution

The EIA does not publish a "data center electricity" line item. We need a proxy.

**Best proxy: Current DC facility count by state (from FracTracker)**

| State | Facilities | Share |
|-------|-----------|-------|
| VA | 450 | 33% |
| GA | 173 | 13% |
| TX | 161 | 12% |
| PA | 87 | 6% |
| OH | 49 | 4% |
| IN | 35 | 3% |
| NY | 32 | 2% |
| IL | 29 | 2% |
| AZ | 27 | 2% |
| CA | 23 | 2% |

**Implementation:** Compute state shares directly from FracTracker facility counts. Store in `data/external/state_shares.csv`. This is more accurate than EIA commercial electricity since it directly reflects where DCs are being built.

**Add a small "exploration" term:** Give states with 0 current facilities a small nonzero probability (e.g., 0.5% split equally) so the simulation can model expansion into new markets.

### Average Project Size

From FracTracker >100MW facilities:
- Mean: ~431 MW (skewed by mega campuses)
- Median: ~200 MW
- **Use 300 MW** as `avg_project_mw` in config (between median and mean, reflects trend toward larger projects)

Monthly candidate count = `(1500 MW/month) / (300 MW/project)` = **5 candidate projects per month**

---

## 6. Dataset 5: Calibration Anchors

These are the external reference points used to calibrate the XGBoost/logistic model output to real-world approval probabilities.

### Anchor 1: National Median (44%)

- **Source:** Heatmap/Embold National Data Center Public Opinion Survey (2025)
- **URL:** https://heatmap.news/politics/data-center-survey
- **Key finding:** 44% of Americans support data center construction in their community
- **How we use it:** The county with the median raw model score gets calibrated to p=0.44
- **Additional findings to extract:**
  - Breakdown by political affiliation (likely: Republicans more supportive)
  - Breakdown by proximity to existing facilities (likely: lower approval if near existing DCs)
  - Top concerns cited (water, power, noise, land use)

### Anchor 2: Loudoun County, VA (75-80%)

- **Source:** JLARC "Data Centers in Virginia" (2024) + historical context
- **URL:** https://jlarc.virginia.gov/landing-2024-data-centers-in-virginia.asp
- **Rationale:** Loudoun has 187 facilities (largest concentration in the world) and maintained high approval through early growth. Recent backlash but historically pro-development.
- **Calibration target:** 0.775 (midpoint)

### Anchor 3: Prince William / Culpeper County, VA (20-30%)

- **Source:** Documented moratoriums and community opposition
- **Rationale:** Both counties have enacted moratoriums or restrictions on new DC construction
- **Calibration target:** 0.25 (midpoint)

### Additional Anchors (aim for 5-6 total)

Search the Data Center Watch and Bryce databases for 2-3 more:
- **Chesterfield County, VA** — documented opposition → calibrate ~30%
- **A Georgia county** with opposition (Jones or Henry County) → calibrate ~35%
- **A Midwest county** with strong support (e.g., Columbus OH area) → calibrate ~60%

### JLARC Report — Key Figures to Extract

This report is critical for calibrating intervention functions:

| Figure | Value | Use |
|--------|-------|-----|
| Virginia DC tax revenue | $1.6-1.9B annually | Validates CEA Florida's $405.8M/GW figure |
| Loudoun County tax share | ~60-70% of VA total | Shows concentration/inequality |
| Electricity cost impact | X% increase in residential rates | Informs community utility calculation |
| Water consumption | Y million gallons/day | Validates water stress feature importance |
| Employment | Z jobs statewide | Cross-check with QWI data |

**Acquisition:** The JLARC report is freely available as PDF from the URL above. Read and extract the specific figures needed.

---

## 7. County FIPS Mapping Pipeline

The FracTracker CSV has `county` (name) and `state` (abbreviation) but NO FIPS codes. This is the most error-prone step.

### Recommended Tool: `addfips` Python library

```bash
pip install addfips
```

```python
import addfips
af = addfips.AddFIPS()

# Example usage
fips = af.get_county_fips("Loudoun", state="Virginia")  # Returns "51107"
fips = af.get_county_fips("Prince William", state="VA")  # Returns "51153"
```

### Known Gotchas

1. **State abbreviations vs full names:** `addfips` accepts both, but be consistent
2. **Name variants:** "St. Louis" vs "Saint Louis", "Prince George's" vs "Prince Georges"
3. **Independent cities:** Virginia has independent cities (e.g., Norfolk, Richmond) that are NOT counties but have their own FIPS codes. The FracTracker data may list these as counties.
4. **Duplicate names:** "Jefferson County" exists in 26 states — always use county+state together
5. **Missing counties:** If `addfips` can't match, fall back to lat/long reverse geocoding using `censusgeocode`

### Validation

After FIPS mapping, verify:
- No null FIPS codes (every row must have a FIPS)
- No impossible FIPS (e.g., state portion of FIPS matches the state column)
- Spot-check top counties: Loudoun=51107, Prince William=51153, Maricopa=04013, Bexar=48029

### Implementation: `src/data/features.py`

```python
def add_fips_codes(df: pd.DataFrame) -> pd.DataFrame:
    """Add 5-digit FIPS codes to DataFrame with county+state columns.

    Uses addfips library with fallback to censusgeocode for failures.
    Validates all FIPS codes are 5 digits and state prefix matches.
    """
```

---

## 8. Data Pipeline Execution Order

This is the sequence for Phase 2 data collection. Each step depends on the previous.

### Step 1: Prepare FracTracker (no external deps)
1. Load CSV
2. Clean/normalize columns
3. Add FIPS codes via `addfips`
4. Filter to Tier 1 (>100MW) and compute Tier 2 saturation counts
5. Aggregate to county level
6. Save to `data/processed/county_facilities.csv`

### Step 2: Collect External Features (parallel, independent)
These can all run in parallel:

| Feature | Source | Method | Output File |
|---------|--------|--------|-------------|
| Water stress | WRI Aqueduct | Spatial join or API | `data/processed/water_stress.csv` |
| Partisan lean | MIT Election Lab | Download CSV | `data/processed/partisan_lean.csv` |
| DC employment | Census QWI API | Python API calls | `data/processed/qwi_employment.csv` |
| State incentives | Good Jobs First | Manual extraction | `data/external/state_incentives.csv` |
| Opposition data | Bryce + DCW | Manual curation | `data/external/bryce_rejections.csv` |

### Step 3: Merge Features into County Matrix
1. Start with `county_facilities.csv` (FIPS-keyed)
2. Left-join each external feature by FIPS
3. Fill missing values: QWI employment → 0, water stress → state median, partisan lean → state average
4. Compute derived features (hyperscaler share, cooling flag, etc.)
5. Add binary outcome column
6. Save to `data/processed/county_feature_matrix.csv`

### Step 4: State-Level Features
1. Compute state incentive scores (uniform per state)
2. Compute state candidate shares from FracTracker facility counts
3. Save to `data/external/state_shares.csv`

### Step 5: Train Model
1. Load county feature matrix
2. Filter to counties with known outcomes (~108 counties)
3. Train XGBoost and logistic regression with 5-fold CV
4. Generate predictions for ALL counties (including those with only proposed projects)
5. Calibrate against anchor points
6. Parameterize as Beta distributions
7. Save to `data/processed/county_approval_probs.csv`

---

## 9. Simulation Implementation Details

### Monthly Simulation Step (Pseudocode)

```
for each month t in [Jan 2026, ..., Dec 2035]:
    # 1. Generate candidates
    n_candidates = monthly_gw / avg_project_mw
    for i in range(n_candidates):
        state = draw_from_multinomial(state_shares)
        county = draw_from_counties_in_state(state)

        # 2. Compute approval probability
        p_base = county_approval_probs[county]

        if interventions.tax_benefit.enabled:
            n = county_saturation[county]
            delta_tax = A * exp(-lambda * n)
        if interventions.employment_benefit.enabled:
            delta_jobs = L * (n / n0) * exp(1 - n / n0)

        p_adjusted = clip(p_base + delta_tax + delta_jobs, 0.05, 0.95)

        # 3. Sample approval
        alpha = p_adjusted * kappa
        beta = (1 - p_adjusted) * kappa
        approval_draw = rng.beta(alpha, beta)

        # 4. Apply threshold
        if scenario.threshold is None:  # laissez-faire
            built = (approval_draw > 0.5)
        elif scenario.firm_borne:
            # firm optimizes: find min cost to push p over threshold
            # if infeasible, built = False
            cost = firm_optimize(p_base, n, threshold, config)
            built = (cost is not None)
        else:
            built = (approval_draw > scenario.threshold)

        # 5. Update state
        if built:
            county_saturation[county] += 1
            record(utility, firm_cost)
```

### Firm Optimization (Scenarios 4-5)

```python
def firm_optimize(p_base, n, threshold, config) -> float | None:
    """Find minimum cost to push expected approval over threshold.

    Solve:
        minimize    cost_tax(s_tax) + cost_jobs(s_jobs)
        subject to  p_base + s_tax * delta_p_tax(n) + s_jobs * delta_p_jobs(n) >= threshold
                    0 <= s_tax <= 1,  0 <= s_jobs <= 1

    Returns total cost, or None if infeasible.

    Implementation: since delta_p_tax(n) and delta_p_jobs(n) are known constants
    for a given n, this is a simple 2-variable LP. Use scipy.optimize.linprog.
    """
```

---

## 10. Visualization Plan

### Static Visualizations (matplotlib/seaborn)

**Viz 1: Cumulative Growth Trajectories**
- X: months (0-120), Y: cumulative facilities built
- 5 lines (one per scenario), mean + shaded 95% CI bands
- This is the hero visualization — directly answers "how do consent regimes alter growth?"

**Viz 2: County-Level Approval Heatmap**
- U.S. county choropleth colored by calibrated approval probability
- Two versions: baseline (no intervention) and with firm-borne consent
- Shows geographic redistribution effect

**Viz 3: Spatial Concentration (Gini Over Time)**
- X: months, Y: Gini coefficient of county build counts
- Shows whether consent regimes spread development more evenly

**Viz 4: Firm Cost vs. Community Benefit Tradeoff**
- Scatter or bar chart: per-scenario total firm consent cost vs. total community surplus
- The key policy insight visualization

**Viz 5: Feature Importance / Model Diagnostics**
- XGBoost feature importance bar chart
- Logistic regression coefficient plot
- Side-by-side comparison validates model agreement

### Interactive Visualization (p5.js)

**Threshold Slider Explorer**
- Slider controls approval threshold X% (0% to 100%)
- Real-time update of:
  - Cumulative growth curve (precomputed for each threshold in 5% increments)
  - Number of facilities built by 2035
  - Average firm consent cost
- Data exported from simulation as JSON (`viz/data/threshold_sweep.json`)

### Presentation Slides

For later (Phase 4), but plan for:
- Causal diagrams (Excalidraw)
- Methodology pipeline figure (already in proposal)
- Key results summary (3-4 slides with one viz each)
- The data journalism article IS the final product — slides supplement it

---

## 11. Known Risks and Mitigations

### Data Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| FracTracker MW data is 69% missing | Can't compute accurate county avg MW | Use sizerank categories instead of raw MW; impute median for missing |
| Cooling type is 98% missing | Feature unusable | Drop cooling_water_intensive; use water_stress as proxy for water concerns |
| QWI may not have 2024-2025 data yet | Employment feature incomplete | Use latest available quarter; note recency in article |
| MIT Election Lab 2024 may not be released | Partisan lean stale | Fall back to 2020 data; note in article |
| WRI Aqueduct requires GIS processing | Complex spatial join | Use county centroid approach; or find pre-processed county dataset |
| Bryce database is in articles, not CSV | Manual extraction needed | Budget 1-2 hours for manual curation; only ~40 rows |

### Modeling Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| 108 training counties is small | Model overfitting | Run logistic regression alongside XGBoost; compare predictions |
| Anchor calibration with 3-4 points is thin | Calibration unreliable | Push for 5-6 anchors; report sensitivity to anchor perturbations |
| Intervention function shapes are assumed | Results depend on assumed curves | ±30% sensitivity analysis; report results across the range |
| 10,000 draws may be slow | Iteration speed | Phase 1 uses 100-1000 draws for development; 10,000 only for final runs |

### Data Quality Checks to Implement

1. **FIPS validation:** Every county has a valid 5-digit FIPS; state prefix matches
2. **Feature bounds:** Water stress in [1,10], partisan lean in [0,1], employment ≥ 0
3. **Outcome balance:** Check class balance of binary outcome (77 approved vs 31 blocked is ~71/29 — moderate imbalance, manageable)
4. **County coverage:** Training counties span ≥ 10 states and both high/low approval
5. **Correlation check:** No two features have |r| > 0.9 (watch saturation_count vs hyperscaler_share)
