"""Noisy availability forecast.

Author: Judith Njoku
"""

from __future__ import annotations

import numpy as np

__author__ = "Judith Njoku"


class NoisyForecastProvider:
    provider_name = "noisy"

    def __init__(self, error_scale: float = 0.20, seed: int = 42):
        self.error_scale = error_scale
        self.rng = np.random.default_rng(seed)

    def forecast(self, model, agent) -> dict[str, float]:
        out: dict[str, float] = {}
        for space_id, state in model.resource_manager.states.items():
            truth = 0.0 if state.occupied or state.unavailable else 1.0
            out[space_id] = float(np.clip(truth + self.rng.normal(0.0, self.error_scale), 0.0, 1.0))
        return out
