"""Tests for src/data/ingest.py — FracTracker loading, FIPS mapping, aggregation."""

import pandas as pd
import pytest

from src.data.ingest import (
    _match_hyperscaler,
    _parse_mw,
    add_fips_codes,
    aggregate_to_county,
    classify_tiers,
    compute_state_shares,
    load_fractracker,
    validate_fips,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_facility_row(**overrides: object) -> dict:
    """Build a single facility row dict with sensible defaults."""
    defaults = {
        "facility_name": "Test DC",
        "address": "123 Main St",
        "city": "TestCity",
        "state": "VA",
        "zip": "20166",
        "county": "Loudoun",
        "lat": "39.0",
        "long": "-77.5",
        "status": "Operating",
        "location_confidence": "High",
        "purpose": "Data Center",
        "operator_name": "Microsoft",
        "tenant": "",
        "mw": "300",
        "sizerank": "Hyperscale (100-999 MW)",
        "power_source": "",
        "dedicated_power_plant": "",
        "number_of_generators": "",
        "number_of_buildings": "",
        "cooling_source": "",
        "cooling_type": "",
        "facility_size_sqft": "",
        "property_size_acres": "",
        "project_cost": "",
        "expected_date_online": "",
        "community_pushback": "",
        "advocacy_information": "",
        "resistance_status": "",
        "nda": "",
        "community_group_website_1": "",
        "community_group_website_2": "",
        "petition_url": "",
        "other_info": "",
        "information_source": "",
        "info_source_1": "",
        "info_source_2": "",
        "info_source_3": "",
        "info_source_4": "",
        "info_source_5": "",
        "info_source_6": "",
        "info_source_7": "",
        "info_source_8": "",
        "date_updated": "",
    }
    defaults.update(overrides)
    return defaults


def _make_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows).astype(str)


# ---------------------------------------------------------------------------
# MW parsing
# ---------------------------------------------------------------------------


class TestParseMW:
    def test_numeric_string(self):
        s = pd.Series(["300", "1200", "150"])
        result = _parse_mw(s)
        assert result.tolist() == [300.0, 1200.0, 150.0]

    def test_with_commas(self):
        s = pd.Series(["1,200", "2,500"])
        result = _parse_mw(s)
        assert result.tolist() == [1200.0, 2500.0]

    def test_with_gt_prefix(self):
        s = pd.Series([">500", ">1000"])
        result = _parse_mw(s)
        assert result.tolist() == [500.0, 1000.0]

    def test_nan_for_missing(self):
        s = pd.Series(["Unknown", "", pd.NA])
        result = _parse_mw(s)
        assert result.isna().all()


# ---------------------------------------------------------------------------
# Hyperscaler matching
# ---------------------------------------------------------------------------


class TestMatchHyperscaler:
    def test_microsoft_variants(self):
        assert _match_hyperscaler("Microsoft") == "Microsoft"
        assert _match_hyperscaler("Microsoft Corporation") == "Microsoft"

    def test_amazon_variants(self):
        assert _match_hyperscaler("Amazon") == "Amazon"
        assert _match_hyperscaler("Amazon Data Services Inc") == "Amazon"

    def test_google(self):
        assert _match_hyperscaler("Google") == "Google"

    def test_non_hyperscaler(self):
        assert _match_hyperscaler("Digital Realty") is None
        assert _match_hyperscaler("STACK INFRASTRUCTURE") is None

    def test_none_and_empty(self):
        assert _match_hyperscaler(None) is None
        assert _match_hyperscaler("") is None
        assert _match_hyperscaler(float("nan")) is None


# ---------------------------------------------------------------------------
# FIPS mapping
# ---------------------------------------------------------------------------


class TestAddFipsCodes:
    def test_known_counties(self):
        rows = [
            _make_facility_row(county="Loudoun", state="VA"),
            _make_facility_row(county="Maricopa", state="AZ"),
            _make_facility_row(county="Bexar", state="TX"),
        ]
        df = add_fips_codes(_make_df(rows))
        assert df["fips"].tolist() == ["51107", "04013", "48029"]

    def test_county_name_corrections(self):
        rows = [
            _make_facility_row(county="Athens-Clark", state="GA"),
            _make_facility_row(county="Spaulding", state="GA"),
            _make_facility_row(county="St Lucie", state="FL"),
        ]
        df = add_fips_codes(_make_df(rows))
        assert df["fips"].tolist() == ["13059", "13255", "12111"]

    def test_lawrence_wy_fix(self):
        """The Lawrence/WY entry is a data error — should map to Lawrence OH."""
        rows = [_make_facility_row(county="Lawrence", state="WY")]
        df = add_fips_codes(_make_df(rows))
        assert df["fips"].iloc[0] == "39087"  # Lawrence County, OH


class TestValidateFips:
    def test_all_valid(self):
        df = pd.DataFrame(
            {
                "fips": ["51107", "04013", "48029"],
                "county": ["a", "b", "c"],
                "state": ["VA", "AZ", "TX"],
            }
        )
        assert validate_fips(df) == []

    def test_null_fips_detected(self):
        df = pd.DataFrame({"fips": ["51107", None], "county": ["a", "b"], "state": ["VA", "TX"]})
        errors = validate_fips(df)
        assert any("null FIPS" in e for e in errors)


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------


class TestClassifyTiers:
    def test_tier1_filters_hyperscale_mega(self):
        rows = [
            _make_facility_row(sizerank="Hyperscale (100-999 MW)"),
            _make_facility_row(sizerank="Mega campus (>1,000 MW)"),
            _make_facility_row(sizerank="Small (0-10 MW)"),
            _make_facility_row(sizerank="Unknown"),
        ]
        df = _make_df(rows)
        tier1, _ = classify_tiers(df)
        assert len(tier1) == 2

    def test_tier2_filters_operating(self):
        rows = [
            _make_facility_row(status="Operating"),
            _make_facility_row(status="Proposed"),
            _make_facility_row(status="Operating"),
        ]
        df = _make_df(rows)
        _, tier2 = classify_tiers(df)
        assert len(tier2) == 2


# ---------------------------------------------------------------------------
# County aggregation
# ---------------------------------------------------------------------------


class TestAggregateToCounty:
    def _setup_data(self):
        tier1_rows = [
            _make_facility_row(
                county="Loudoun",
                state="VA",
                mw="300",
                status="Operating",
                community_pushback="Yes",
                operator_name="Amazon",
            ),
            _make_facility_row(
                county="Loudoun",
                state="VA",
                mw="500",
                status="Operating",
                community_pushback="",
                operator_name="Google",
            ),
            _make_facility_row(
                county="Maricopa",
                state="AZ",
                mw="200",
                status="Suspended",
                community_pushback="",
                operator_name="Digital Realty",
            ),
        ]
        tier2_rows = [
            _make_facility_row(county="Loudoun", state="VA", status="Operating"),
            _make_facility_row(county="Loudoun", state="VA", status="Operating"),
            _make_facility_row(county="Loudoun", state="VA", status="Operating"),
            _make_facility_row(county="Maricopa", state="AZ", status="Operating"),
        ]
        # Build DataFrames with needed columns by running through add_fips_codes
        t1 = add_fips_codes(_make_df(tier1_rows))
        t1["mw_numeric"] = _parse_mw(t1["mw"])
        t1["pushback"] = t1["community_pushback"].str.lower().str.strip() == "yes"
        t1["hyperscaler_name"] = t1["operator_name"].map(_match_hyperscaler)
        t1["is_hyperscaler"] = t1["hyperscaler_name"].notna()

        t2 = add_fips_codes(_make_df(tier2_rows))
        t2["mw_numeric"] = _parse_mw(t2["mw"])
        t2["pushback"] = t2["community_pushback"].str.lower().str.strip() == "yes"
        t2["hyperscaler_name"] = t2["operator_name"].map(_match_hyperscaler)
        t2["is_hyperscaler"] = t2["hyperscaler_name"].notna()

        return t1, t2

    def test_county_count(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        assert len(county) == 2  # Loudoun + Maricopa

    def test_facility_count(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        loudoun = county[county["fips"] == "51107"].iloc[0]
        assert loudoun["facility_count"] == 2

    def test_saturation_from_tier2(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        loudoun = county[county["fips"] == "51107"].iloc[0]
        assert loudoun["saturation_count"] == 3  # 3 Operating in tier2

    def test_pushback_flag(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        loudoun = county[county["fips"] == "51107"].iloc[0]
        maricopa = county[county["fips"] == "04013"].iloc[0]
        assert loudoun["pushback_flag"] == 1
        assert maricopa["pushback_flag"] == 0

    def test_hyperscaler_share(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        loudoun = county[county["fips"] == "51107"].iloc[0]
        assert loudoun["hyperscaler_share"] == 1.0  # Amazon + Google, both hyperscalers

    def test_binary_outcome(self):
        t1, t2 = self._setup_data()
        county = aggregate_to_county(t1, t2)
        loudoun = county[county["fips"] == "51107"].iloc[0]
        maricopa = county[county["fips"] == "04013"].iloc[0]
        assert loudoun["binary_outcome"] == 1.0  # Both Operating = approved
        assert maricopa["binary_outcome"] == 0.0  # Suspended = blocked


# ---------------------------------------------------------------------------
# State shares
# ---------------------------------------------------------------------------


class TestComputeStateShares:
    def test_shares_sum_to_one(self):
        df = _make_df(
            [
                _make_facility_row(state="VA"),
                _make_facility_row(state="VA"),
                _make_facility_row(state="TX"),
            ]
        )
        df = add_fips_codes(df)
        shares = compute_state_shares(df)
        assert shares["adjusted_share"].sum() == pytest.approx(1.0, abs=1e-6)

    def test_all_51_entries(self):
        df = _make_df([_make_facility_row(state="VA")])
        df = add_fips_codes(df)
        shares = compute_state_shares(df)
        assert len(shares) == 51  # 50 states + DC

    def test_exploration_term(self):
        df = _make_df([_make_facility_row(state="VA")])
        df = add_fips_codes(df)
        shares = compute_state_shares(df, exploration_pct=0.005)
        zero_states = shares[shares["facility_count"] == 0]
        assert all(zero_states["adjusted_share"] > 0)

    def test_zero_exploration(self):
        df = _make_df([_make_facility_row(state="VA")])
        df = add_fips_codes(df)
        shares = compute_state_shares(df, exploration_pct=0.0)
        zero_states = shares[shares["facility_count"] == 0]
        assert all(zero_states["adjusted_share"] == 0)


# ---------------------------------------------------------------------------
# Full pipeline integration test
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_load_fractracker_runs(self):
        """Smoke test: the real FracTracker CSV loads without error."""
        df = load_fractracker()
        assert len(df) > 1000
        assert "fips" in df.columns
        assert "mw_numeric" in df.columns

    def test_fips_validation_passes(self):
        """Real data should have zero FIPS validation errors."""
        df = load_fractracker()
        errors = validate_fips(df)
        assert errors == []

    def test_tier_split(self):
        df = load_fractracker()
        tier1, tier2 = classify_tiers(df)
        assert 300 <= len(tier1) <= 400  # ~337
        assert 400 <= len(tier2) <= 600  # ~492

    def test_county_aggregation(self):
        df = load_fractracker()
        tier1, tier2 = classify_tiers(df)
        county = aggregate_to_county(tier1, tier2)
        # Should have 200-250 counties
        assert 200 <= len(county) <= 260
        # Loudoun should be present
        assert "51107" in county["fips"].values

    def test_outcome_distribution(self):
        """Training set should have ~108 counties with known outcomes."""
        df = load_fractracker()
        tier1, tier2 = classify_tiers(df)
        county = aggregate_to_county(tier1, tier2)
        n_with_outcome = county["binary_outcome"].notna().sum()
        assert 90 <= n_with_outcome <= 130  # ~108 expected
