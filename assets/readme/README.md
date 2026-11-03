# README illustrations

These files accompany the root README and are included in the repository.

- [cesium-platform.jpg](cesium-platform.jpg) shows the deployed Cesium website on 3 November 2026. The lot, two store doors and two vehicle entry/exit points are visible. This is a screenshot of a simulation, not a live occupancy feed.
- [walmart-layout.png](walmart-layout.png) shows the estimated parking spaces and connected aisle network over the satellite image used for site review. Google Maps branding and imagery attribution are retained. The [layout provenance](walmart-layout-provenance.json) records the approximate georeferencing and configuration hash.
- [parking-model-comparison.png](parking-model-comparison.png) shows search duration, walking distance and parking success for the three primary decision models and two comparison controls at 80% and 95% initial occupancy. Markers show condition means from 30 replications; uncertainty intervals are not displayed in this illustration. The [aggregate source table](parking-model-comparison.csv) contains the values used by the figure.

The website uses CesiumJS and OpenStreetMap imagery; see [platform attribution](../../dashboard/THIRD_PARTY.md). Geometry and driver behavior are simulation assumptions. These illustrations do not establish survey accuracy or field validation.

[provenance.json](provenance.json) records the original local source paths and SHA-256 digests. Those source paths identify the preparation files; the README uses only the copies in this folder.
