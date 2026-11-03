"""Perfect forecast control condition.

Author: Judith Njoku
"""

from __future__ import annotations

__author__ = "Judith Njoku"


class PerfectForecastProvider:
    provider_name = "perfect"

    def forecast(self, model, agent) -> dict[str, float]:
        return {
            space_id: 0.0 if state.occupied or state.unavailable else 1.0
            for space_id, state in model.resource_manager.states.items()
        }
