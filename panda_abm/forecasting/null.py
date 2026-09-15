"""No forecast information.

Author: Judith Njoku
"""

from __future__ import annotations

__author__ = "Judith Njoku"


class NullForecastProvider:
    provider_name = "null"

    def forecast(self, model, agent) -> dict[str, float]:
        return {}
