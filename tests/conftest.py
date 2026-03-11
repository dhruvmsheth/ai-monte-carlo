import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def rng():
    """Seeded random number generator for reproducible tests."""
    return np.random.default_rng(seed=12345)


@pytest.fixture
def tiny_counties():
    """3 counties with known features for deterministic testing."""
    return pd.DataFrame(
        {
            "fips": ["51107", "51153", "06085"],
            "name": ["Loudoun County, VA", "Prince William County, VA", "Santa Clara County, CA"],
            "state": ["VA", "VA", "CA"],
            "saturation_count": [15, 3, 7],
            "water_stress_decile": [4, 6, 8],
            "dc_employment": [5000, 200, 3000],
            "partisan_lean_r": [0.45, 0.42, 0.30],
            "pushback_flag": [0, 1, 0],
            "state_incentive_generosity": [0.7, 0.7, 0.5],
            "project_mw_avg": [400, 200, 350],
            "cooling_water_intensive": [0, 1, 0],
            "hyperscaler_share": [0.8, 0.3, 0.6],
            "base_approval_p": [0.775, 0.25, 0.50],
        }
    )
