"""Local metric approximation used by the estimated Laramie lot layout."""

import math


def lat_lon_to_local_m(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """East/north metres, matching the existing config's 111,000 m/degree scale.

    This small-site approximation is not a survey coordinate reference system.
    """
    return (
        (lon - ref_lon) * 111_000.0 * math.cos(math.radians(ref_lat)),
        (lat - ref_lat) * 111_000.0,
    )
