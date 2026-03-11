"""Tests for src/simulation/state.py — CountyState, SimulationState, mutations, snapshots."""

from src.simulation.state import CountyState, SimulationState


def _make_county(fips: str = "51107", name: str = "Loudoun", state: str = "VA") -> CountyState:
    return CountyState(
        fips=fips,
        name=name,
        state=state,
        saturation_count=5,
        base_approval_p=0.775,
    )


def _make_state(counties: dict[str, CountyState] | None = None) -> SimulationState:
    if counties is None:
        counties = {
            "51107": _make_county("51107", "Loudoun", "VA"),
            "06085": _make_county("06085", "Santa Clara", "CA"),
        }
    return SimulationState(month=1, year=2026, counties=counties)


class TestCountyState:
    def test_defaults(self):
        c = _make_county()
        assert c.total_mw_built == 0.0
        assert c.features == {}

    def test_features_independent(self):
        c1 = _make_county()
        c2 = _make_county()
        c1.features["water_stress"] = 4
        assert "water_stress" not in c2.features


class TestIncrementSaturation:
    def test_increments_by_one(self):
        s = _make_state()
        initial = s.counties["51107"].saturation_count
        s.increment_saturation("51107")
        assert s.counties["51107"].saturation_count == initial + 1

    def test_does_not_affect_other_county(self):
        s = _make_state()
        initial_other = s.counties["06085"].saturation_count
        s.increment_saturation("51107")
        assert s.counties["06085"].saturation_count == initial_other


class TestRecordBuild:
    def test_updates_county_and_national(self):
        s = _make_state()
        s.record_build("51107", mw=300.0)
        assert s.counties["51107"].total_mw_built == 300.0
        assert s.counties["51107"].saturation_count == 6  # was 5
        assert s.national_total_mw == 300.0
        assert s.national_facilities == 1

    def test_multiple_builds(self):
        s = _make_state()
        s.record_build("51107", mw=300.0)
        s.record_build("06085", mw=200.0)
        s.record_build("51107", mw=150.0)
        assert s.counties["51107"].total_mw_built == 450.0
        assert s.counties["06085"].total_mw_built == 200.0
        assert s.national_total_mw == 650.0
        assert s.national_facilities == 3


class TestGetSnapshot:
    def test_empty_state(self):
        s = _make_state()
        snap = s.get_snapshot()
        assert snap["month"] == 1
        assert snap["year"] == 2026
        assert snap["national_total_mw"] == 0.0
        assert snap["national_facilities"] == 0
        assert snap["counties_with_builds"] == 0
        assert snap["total_saturation"] == 10  # 5 + 5 from both counties

    def test_after_builds(self):
        s = _make_state()
        s.record_build("51107", mw=300.0)
        snap = s.get_snapshot()
        assert snap["national_total_mw"] == 300.0
        assert snap["national_facilities"] == 1
        assert snap["counties_with_builds"] == 1
        assert snap["total_saturation"] == 11  # 6 + 5

    def test_snapshot_is_dict(self):
        s = _make_state()
        snap = s.get_snapshot()
        assert isinstance(snap, dict)
