"""Simulation state dataclasses: mutable state for a single Monte Carlo draw."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CountyState:
    """Mutable state for a single county during a simulation draw."""

    fips: str
    name: str
    state: str
    saturation_count: int
    base_approval_p: float
    total_mw_built: float = 0.0
    features: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationState:
    """Mutable aggregate state for one simulation draw across all counties."""

    month: int  # 1-indexed month within the simulation (1 = first month)
    year: int
    counties: dict[str, CountyState] = field(default_factory=dict)  # keyed by FIPS
    national_total_mw: float = 0.0
    national_facilities: int = 0

    def increment_saturation(self, fips: str) -> None:
        """Bump saturation count by 1 for the given county."""
        self.counties[fips].saturation_count += 1

    def record_build(self, fips: str, mw: float) -> None:
        """Record a facility build in a county and update national totals."""
        county = self.counties[fips]
        county.total_mw_built += mw
        county.saturation_count += 1
        self.national_total_mw += mw
        self.national_facilities += 1

    def get_snapshot(self) -> dict[str, Any]:
        """Return a dict of current aggregate metrics for time-series recording."""
        return {
            "month": self.month,
            "year": self.year,
            "national_total_mw": self.national_total_mw,
            "national_facilities": self.national_facilities,
            "counties_with_builds": sum(1 for c in self.counties.values() if c.total_mw_built > 0),
            "total_saturation": sum(c.saturation_count for c in self.counties.values()),
        }
