"""Build opposition.csv from researched data center rejection/moratorium cases.

Sources:
- Robert Bryce's Data Center Rejection Database (Substack)
- Data Center Watch Q2 2025 report ($98B blocked/delayed)
- Heatmap News, Gizmodo, GPB, DCD, Virginia Mercury, IBJ, etc.

Each row: county, state, opposition_type, source
FIPS codes added via addfips library.
"""

import csv
import sys
from pathlib import Path

import addfips

# All researched cases.
# Format: (county, state, opposition_type, source)
# opposition_type: moratorium | ban | ordinance | cancelled | delayed | rejected
# source: bryce | datacenterwatch | news

CASES: list[tuple[str, str, str, str]] = [
    # =========================================================================
    # VIRGINIA — Epicenter of opposition
    # =========================================================================
    # Prince William County — $24.7B PW Digital Gateway (QTS/Compass), multiple lawsuits
    ("Prince William", "Virginia", "delayed", "datacenterwatch"),
    # Culpeper County — $12B project, Planning Commission unanimously denied rezoning Jun 2024
    ("Culpeper", "Virginia", "rejected", "datacenterwatch"),
    # King George County — $6B Amazon project, board voted to renegotiate/reverse rezoning
    ("King George", "Virginia", "delayed", "datacenterwatch"),
    # Pittsylvania County — Balico $8.85B campus + 3500MW gas plant, withdrawn Apr 2025
    ("Pittsylvania", "Virginia", "cancelled", "news"),
    # Louisa County — Amazon $1B campus, withdrawn Jul 2025 after community opposition
    ("Louisa", "Virginia", "cancelled", "news"),
    # Charles City County — Kansas-based developer withdrew rezoning Aug 2025
    ("Charles City", "Virginia", "cancelled", "news"),
    # Richmond city — DC Blox $500M, withdrawn after planning deferral
    ("Richmond city", "Virginia", "cancelled", "datacenterwatch"),
    # Fauquier County (Catlett Station) — Headwaters $400M, withdrawn before hearing
    ("Fauquier", "Virginia", "cancelled", "datacenterwatch"),
    # Powhatan County (Midlothian area) — Province Group $3B, delayed
    ("Powhatan", "Virginia", "delayed", "datacenterwatch"),
    # Alexandria — Starwood $165M Plaza 500, deferred indefinitely
    ("Alexandria city", "Virginia", "delayed", "datacenterwatch"),
    # Warrenton (Fauquier County) — Amazon 220K sqft, legal challenges + council turnover
    # Already have Fauquier above; Warrenton is independent town in Fauquier area
    # Manassas — Amazon Ashton proposal, planning commission opposed, withdrawn
    ("Manassas city", "Virginia", "cancelled", "datacenterwatch"),
    # Loudoun County — zoning reform to prohibit by-right data centers
    ("Loudoun", "Virginia", "ordinance", "news"),

    # =========================================================================
    # GEORGIA — Wave of ordinances and moratoriums
    # =========================================================================
    # Pike County — moratorium Sep 2024
    ("Pike", "Georgia", "moratorium", "news"),
    # Lamar County — moratorium Sep 2024
    ("Lamar", "Georgia", "moratorium", "news"),
    # Troup County — moratorium Sep 2024
    ("Troup", "Georgia", "moratorium", "news"),
    # Clayton County — 120-day moratorium 2024
    ("Clayton", "Georgia", "moratorium", "news"),
    # Coweta County — 180-day moratorium May 2024
    ("Coweta", "Georgia", "moratorium", "news"),
    # Bartow County — ordinance (noise restrictions, 200ft buffer) Jan 2025
    ("Bartow", "Georgia", "ordinance", "news"),
    # Jones County — ordinance requiring closed-loop water
    ("Jones", "Georgia", "ordinance", "news"),
    # DeKalb County — ordinance with tiered categories
    ("DeKalb", "Georgia", "ordinance", "news"),
    # Lumpkin County — ordinance with restrictions on "compute centers"
    ("Lumpkin", "Georgia", "ordinance", "news"),
    # Forsyth County — ordinance prohibiting cooling systems from using county water
    ("Forsyth", "Georgia", "ordinance", "news"),
    # Newton County — Meta facility, community water concerns
    ("Newton", "Georgia", "ordinance", "news"),

    # =========================================================================
    # INDIANA — Multiple county moratoriums and project withdrawals
    # =========================================================================
    # Marion County (Indianapolis/Franklin Township) — Google 468-acre, withdrawn Sep 2025
    ("Marion", "Indiana", "cancelled", "news"),
    # Marshall County — first IN county moratorium, Feb 2025
    ("Marshall", "Indiana", "moratorium", "news"),
    # White County — moratorium Oct 2025
    ("White", "Indiana", "moratorium", "news"),
    # Putnam County — one-year moratorium Nov 2025
    ("Putnam", "Indiana", "moratorium", "news"),
    # Fulton County — one-year moratorium, approved after heated hearing
    ("Fulton", "Indiana", "moratorium", "news"),
    # Starke County — one-year moratorium Dec 2025
    ("Starke", "Indiana", "moratorium", "news"),
    # Porter County (Chesterton) — Provident $1.3B, withdrawn
    ("Porter", "Indiana", "cancelled", "datacenterwatch"),
    # Porter County (Burns Harbor) — Provident, withdrawn Oct 2024
    # Same county as Chesterton, already covered above

    # =========================================================================
    # MISSOURI
    # =========================================================================
    # St. Charles (city) — first-in-nation citywide DC ban, Aug 2025
    ("St. Charles", "Missouri", "ban", "news"),
    # Cass County (Peculiar) — zoning amended to prohibit DCs, Oct 2024
    ("Cass", "Missouri", "ban", "news"),

    # =========================================================================
    # MARYLAND
    # =========================================================================
    # Prince George's County — 180-day moratorium, 20K+ petition signatures
    ("Prince George's", "Maryland", "moratorium", "news"),

    # =========================================================================
    # ARIZONA
    # =========================================================================
    # Maricopa County (Goodyear/Buckeye) — $14B withdrawn
    ("Maricopa", "Arizona", "cancelled", "datacenterwatch"),
    # Maricopa County (Chandler) — Active Infrastructure $2.5B unanimously rejected Dec 2025
    # Same county, different city — already captured above
    # Pima County (Tucson) — AWS facility opposition
    ("Pima", "Arizona", "delayed", "news"),

    # =========================================================================
    # OREGON
    # =========================================================================
    # Hood River County (Cascade Locks) — $100M Roundhouse, cancelled after recall election
    ("Hood River", "Oregon", "cancelled", "datacenterwatch"),
    # Wasco County (The Dalles) — Google water controversy, public records disputes
    ("Wasco", "Oregon", "ordinance", "news"),

    # =========================================================================
    # PENNSYLVANIA
    # =========================================================================
    # Lackawanna County (Blakely) — DC proposal withdrawn Sep 2025
    ("Lackawanna", "Pennsylvania", "cancelled", "news"),
    # Chester County (East Vincent Twp) — opposition to DC campus, water concerns
    ("Chester", "Pennsylvania", "delayed", "news"),

    # =========================================================================
    # KENTUCKY
    # =========================================================================
    # Oldham County — Western Hospitality Partners $6B, withdrawn Jul 2025
    ("Oldham", "Kentucky", "cancelled", "news"),

    # =========================================================================
    # KANSAS
    # =========================================================================
    # Wyandotte County (Kansas City) — Red Wolf $12B, lawsuit + delayed
    ("Wyandotte", "Kansas", "delayed", "news"),

    # =========================================================================
    # TENNESSEE
    # =========================================================================
    # Shelby County (South Memphis) — xAI Colossus, environmental justice fight
    ("Shelby", "Tennessee", "delayed", "news"),

    # =========================================================================
    # TEXAS
    # =========================================================================
    # Tarrant County (Fort Worth) — $750M, zoning commission voted against
    ("Tarrant", "Texas", "delayed", "datacenterwatch"),

    # =========================================================================
    # CALIFORNIA
    # =========================================================================
    # Santa Clara County — GI Partners $79M, planning denied then approved on appeal
    ("Santa Clara", "California", "delayed", "datacenterwatch"),

    # =========================================================================
    # NEW JERSEY
    # =========================================================================
    # Middlesex County (New Brunswick) — council abandoned DC proposal, built park instead
    ("Middlesex", "New Jersey", "rejected", "news"),

    # =========================================================================
    # MAINE
    # =========================================================================
    # Androscoggin County (Lewiston) — $300M AI DC unanimously rejected
    ("Androscoggin", "Maine", "rejected", "news"),

    # =========================================================================
    # GEORGIA — Atlanta (Fulton County) — DC prohibition within Beltline overlay
    # =========================================================================
    ("Fulton", "Georgia", "ban", "news"),

    # =========================================================================
    # City of LaGrange, GA — moratorium Sep 2024 (Troup County already covered)
    # LaGrange is in Troup County, already captured
    # =========================================================================
]


def main() -> None:
    af = addfips.AddFIPS()
    output_path = Path(__file__).resolve().parent.parent / "data" / "external" / "opposition.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    failures: list[tuple[str, str]] = []

    for county, state, opposition_type, source in CASES:
        fips = af.get_county_fips(county, state)
        if fips is None:
            failures.append((county, state))
            print(f"WARNING: Could not resolve FIPS for {county}, {state}", file=sys.stderr)
            continue
        rows.append({
            "fips": fips,
            "county": county,
            "state": state,
            "opposition_type": opposition_type,
            "source": source,
        })

    # Deduplicate by FIPS (keep first/strongest opposition type)
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        if row["fips"] not in seen:
            seen.add(row["fips"])
            deduped.append(row)

    # Sort by FIPS
    deduped.sort(key=lambda r: r["fips"])

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["fips", "county", "state", "opposition_type", "source"])
        writer.writeheader()
        writer.writerows(deduped)

    print(f"Wrote {len(deduped)} rows to {output_path}")
    if failures:
        print(f"\n{len(failures)} FIPS lookup failures:", file=sys.stderr)
        for county, state in failures:
            print(f"  - {county}, {state}", file=sys.stderr)


if __name__ == "__main__":
    main()
