"""
Author: Judith Njoku
"""

from __future__ import annotations

from enum import Enum


class DriverState(str, Enum):
    """Sequential parking-search state for a driver agent."""

    NOT_ARRIVED = "not_arrived"
    ARRIVING = "arriving"
    SEARCHING = "searching"
    TARGETING = "targeting"
    PARKED = "parked"
    WALKING_TO_DESTINATION = "walking_to_destination"
    AT_DESTINATION = "at_destination"
    RETURNING_TO_VEHICLE = "returning_to_vehicle"
    EXITING = "exiting"
    LEFT = "left"
    ABANDONED = "abandoned"


class SpaceType(str, Enum):
    """Physical/regulatory class of a parking space."""

    REGULAR = "regular"
    ACCESSIBLE = "accessible"
    RESERVED = "reserved"
    LOADING = "loading"
    EV_CHARGING = "ev_charging"


class StateProvenance(str, Enum):
    """Source/meaning of a parking digital-twin state."""

    OBSERVED_CURRENT = "observed_current"
    SIMULATED_CURRENT = "simulated_current"
    PREDICTED_FUTURE = "predicted_future"
    COUNTERFACTUAL_FUTURE = "counterfactual_future"
