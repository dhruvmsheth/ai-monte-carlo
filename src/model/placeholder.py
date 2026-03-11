"""Placeholder approval model — hardcoded probabilities for simulation development.

Implements the ApprovalModel protocol with manually researched county probabilities.
Used when config sets approval.provider = "placeholder".
"""

from __future__ import annotations

from src.model.protocol import p_to_beta_params

# Manually researched approval probabilities for key counties.
# Sources: JLARC 2024, Data Center Watch, Heatmap/Embold survey, Bryce DB.
_PLACEHOLDER_PROBS: dict[str, float] = {
    # Virginia — epicenter
    "51107": 0.775,  # Loudoun — JLARC 2024, historical high approval
    "51153": 0.25,  # Prince William — documented moratorium
    "51059": 0.70,  # Fairfax — pro-development
    "51033": 0.30,  # Culpeper — rejected rezoning
    "51099": 0.35,  # King George — board reversed rezoning
    "51143": 0.30,  # Pittsylvania — $8.85B campus withdrawn
    "51041": 0.65,  # Chesterfield — active development
    "51087": 0.70,  # Henrico — pro-business
    # Texas
    "48439": 0.80,  # Tarrant — large but some resistance
    "48029": 0.85,  # Bexar — pro-development
    "48113": 0.80,  # Dallas
    "48201": 0.80,  # Harris (Houston)
    # Georgia
    "13135": 0.55,  # Gwinnett — growing opposition
    "13121": 0.45,  # Fulton — Atlanta, DC ban in Beltline overlay
    "13089": 0.60,  # DeKalb — ordinance with restrictions
    # Arizona
    "04013": 0.50,  # Maricopa — $14B withdrawn + water concerns
    "04019": 0.45,  # Pima — AWS opposition
    # Midwest
    "18097": 0.55,  # Marion (Indianapolis) — Google withdrew
    "39049": 0.75,  # Franklin (Columbus, OH) — Intel corridor
    "17031": 0.65,  # Cook (Chicago)
    # Oregon
    "41065": 0.35,  # Wasco — Google water controversy
    "41027": 0.25,  # Hood River — cancelled after recall
    # Northeast
    "42091": 0.65,  # Montgomery (PA)
    "34023": 0.50,  # Middlesex (NJ) — council abandoned DC
    # Nevada
    "32003": 0.80,  # Clark (Las Vegas) — Switch/others
}

# Default probability for counties not in the lookup
_DEFAULT_P: float = 0.44  # National median from Heatmap/Embold 2025 survey


class PlaceholderModel:
    """Placeholder approval model with hardcoded per-county probabilities."""

    def __init__(self, default_p: float = _DEFAULT_P) -> None:
        self._probs = dict(_PLACEHOLDER_PROBS)
        self._default_p = default_p

    def predict_proba(self, fips: str) -> float:
        """Return approval probability for a county."""
        return self._probs.get(fips, self._default_p)

    def get_beta_params(self, fips: str, kappa: float = 40.0) -> tuple[float, float]:
        """Return Beta(α, β) parameters for a county."""
        p = self.predict_proba(fips)
        return p_to_beta_params(p, kappa)

    def feature_names(self) -> list[str]:
        """Placeholder has no real features."""
        return []

    def feature_importances(self) -> dict[str, float]:
        """Placeholder has no feature importances."""
        return {}

    def predict_all(self, fips_list: list[str]) -> dict[str, float]:
        """Return probabilities for a list of FIPS codes."""
        return {fips: self.predict_proba(fips) for fips in fips_list}
