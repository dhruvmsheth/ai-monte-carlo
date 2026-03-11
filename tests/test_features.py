"""Tests for src/data/features.py — external data enrichment and feature matrix."""

import pandas as pd
import pytest

from src.data.features import (
    build_feature_matrix,
    enrich_county_features,
    load_opposition_data,
    load_partisan_lean,
    load_qwi_employment,
    load_state_incentives,
    load_water_stress,
    merge_external_features,
)


def _make_county_df() -> pd.DataFrame:
    """Minimal county DataFrame matching aggregate_to_county output."""
    return pd.DataFrame(
        {
            "fips": ["51107", "51153", "04013"],
            "county": ["Loudoun", "Prince William", "Maricopa"],
            "state": ["VA", "VA", "AZ"],
            "facility_count": [20, 5, 12],
            "total_mw": [6000.0, 1500.0, 3600.0],
            "avg_project_mw": [300.0, 300.0, 300.0],
            "saturation_count": [15, 3, 9],
            "pushback_flag": [0, 1, 0],
            "hyperscaler_share": [0.8, 0.3, 0.5],
            "binary_outcome": [1.0, 0.0, 1.0],
        }
    )


class TestStateIncentiveScores:
    def test_loads_from_csv(self):
        """Real state_incentives.csv should load with correct scores."""
        si = load_state_incentives()
        assert len(si) == 51  # 50 states + DC
        va = si[si["state"] == "VA"]["incentive_score"].iloc[0]
        assert va == 1.0  # VA is most generous per GJF research

    def test_enrichment_uses_csv_scores(self):
        df = _make_county_df()
        enriched = enrich_county_features(df)
        assert "state_incentive_score" in enriched.columns
        va_score = enriched[enriched["state"] == "VA"]["state_incentive_score"].iloc[0]
        assert va_score == 1.0  # From CSV, not hardcoded
        az_score = enriched[enriched["state"] == "AZ"]["state_incentive_score"].iloc[0]
        assert az_score == 0.75  # AZ has DC tax exemptions per GJF

    def test_missing_csv_defaults_to_neutral(self):
        df = _make_county_df()
        enriched = enrich_county_features(df, state_incentives_path="/nonexistent/path.csv")
        assert all(enriched["state_incentive_score"] == 0.50)


class TestEnrichCountyFeatures:
    def test_adds_placeholder_columns(self):
        df = _make_county_df()
        enriched = enrich_county_features(df)
        assert "water_stress_decile" in enriched.columns
        assert "partisan_lean_r" in enriched.columns
        assert "dc_employment" in enriched.columns
        assert "dc_employment_growth" in enriched.columns

    def test_does_not_mutate_input(self):
        df = _make_county_df()
        original_cols = set(df.columns)
        enrich_county_features(df)
        assert set(df.columns) == original_cols


class TestLoadExternalData:
    def test_water_stress_missing_file(self):
        result = load_water_stress("/nonexistent/path.csv")
        assert len(result) == 0
        assert "fips" in result.columns

    def test_partisan_lean_missing_file(self):
        result = load_partisan_lean("/nonexistent/path.csv")
        assert len(result) == 0

    def test_opposition_missing_file(self):
        result = load_opposition_data("/nonexistent/path.csv")
        assert len(result) == 0

    def test_real_water_stress_loads(self):
        ws = load_water_stress()
        assert len(ws) > 3000
        assert ws["water_stress_decile"].between(1, 10).all()

    def test_real_partisan_lean_loads(self):
        pl = load_partisan_lean()
        assert len(pl) > 3000
        assert pl["partisan_lean_r"].between(0, 1).all()

    def test_real_opposition_loads(self):
        opp = load_opposition_data()
        assert len(opp) >= 40
        assert "fips" in opp.columns

    def test_real_qwi_loads(self):
        qwi = load_qwi_employment()
        assert len(qwi) > 1000
        assert "dc_employment" in qwi.columns
        assert (qwi["dc_employment"] >= 0).all()


class TestMergeExternalFeatures:
    def test_water_stress_merge(self):
        df = enrich_county_features(_make_county_df())
        ws = pd.DataFrame({"fips": ["51107", "04013"], "water_stress_decile": [4, 7]})
        merged = merge_external_features(df, water_stress=ws)
        assert merged[merged["fips"] == "51107"]["water_stress_decile"].iloc[0] == 4
        assert merged[merged["fips"] == "04013"]["water_stress_decile"].iloc[0] == 7

    def test_partisan_lean_merge(self):
        df = enrich_county_features(_make_county_df())
        pl = pd.DataFrame({"fips": ["51107"], "partisan_lean_r": [0.45]})
        merged = merge_external_features(df, partisan_lean=pl)
        assert merged[merged["fips"] == "51107"]["partisan_lean_r"].iloc[0] == pytest.approx(0.45)

    def test_opposition_additive(self):
        """Opposition merge should add to existing pushback flags, never remove."""
        df = enrich_county_features(_make_county_df())
        opp = pd.DataFrame(
            {
                "fips": ["04013"],  # Maricopa currently has pushback_flag=0
                "county": ["Maricopa"],
                "state": ["AZ"],
                "opposition_type": ["moratorium"],
                "source": ["bryce"],
            }
        )
        merged = merge_external_features(df, opposition=opp)
        assert merged[merged["fips"] == "04013"]["pushback_flag"].iloc[0] == 1
        assert merged[merged["fips"] == "51153"]["pushback_flag"].iloc[0] == 1

    def test_empty_externals_no_change(self):
        df = enrich_county_features(_make_county_df())
        merged = merge_external_features(df)
        assert len(merged) == len(df)


class TestBuildFeatureMatrix:
    def test_returns_enriched_df(self):
        df = _make_county_df()
        result = build_feature_matrix(df)
        assert "state_incentive_score" in result.columns
        assert len(result) == 3

    def test_real_data_merges_correctly(self):
        """With real external data files, features should be populated."""
        df = _make_county_df()
        result = build_feature_matrix(df)
        # Water stress should be filled for all 3 counties
        assert result["water_stress_decile"].notna().sum() == 3
        # Partisan lean should be filled for at least 2 (Loudoun + Maricopa are in dataset)
        assert result["partisan_lean_r"].notna().sum() >= 2
        # Maricopa should gain pushback from opposition data
        assert result[result["fips"] == "04013"]["pushback_flag"].iloc[0] == 1
        # Loudoun should have QWI employment > 0
        loudoun_emp = result[result["fips"] == "51107"]["dc_employment"].iloc[0]
        assert loudoun_emp > 0

    def test_writes_csv(self, tmp_path):
        df = _make_county_df()
        out = tmp_path / "features.csv"
        build_feature_matrix(df, output_path=out)
        assert out.exists()
        loaded = pd.read_csv(out)
        assert len(loaded) == 3
