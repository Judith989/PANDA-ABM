"""Forecast-provider protocol.

Author: Judith Njoku
"""

from __future__ import annotations

from typing import Protocol

__author__ = "Judith Njoku"


class ForecastProvider(Protocol):
    """Forecasts availability without changing the true parking state."""

    provider_name: str

    def forecast(self, model, agent) -> dict[str, float]:
        ...
