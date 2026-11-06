# Multiple parking environments

## Walking-network update — 2026-11-05

All four built-in environments now provide explicit pedestrian graphs. Downtown uses its OSM-plus-estimated-connection network. Both Walmart layouts use OSM building/road obstacles and estimated internal shared-space routes; the downloaded Walmart extract contains no mapped footways inside the selected facility scope. The fictional transfer uses generated paths and is not presented as an OSM-mapped real site. Network distance now governs preferences, walking limits, references, timing and animation. Old replay files retain their original geometry and walking method. See `research/walmart_pedestrians_20261105/README.md` for sources, backups, overlays and checks. Historical straight-line descriptions below apply to archived configurations.

The Environment selector includes Walmart, the separate fictional synthetic transfer layout, and Downtown Laramie with street parking and 3D building context. Downtown is an image-derived experimental reconstruction, not a surveyed site. Switching environments closes the current simulation and clears its supply selections. Saved replays retain their environment configuration.

## Import and align

1. Open **Import a 3D environment** and download the JSON template. Replace its example geometry with the new lot's coordinates and routes.
2. Select the lot JSON and, optionally, its self-contained GLB 2.0 files. Use embedded buffers/textures, at most eight files, 100 MB per model and 200 MB total. Models exported together must share a coordinate frame. External-resource glTF, OBJ, FBX, 3D Tiles and Cesium ion assets are not supported by this importer.
3. Choose **Validate and preview**. Validation checks numeric coordinates, unique IDs, usable inventory, door/access definitions, complete road assignments and connected routes. Door and exit distances are recalculated from the supplied coordinates.
4. Inspect the spaces, door/access markers and aisle overlay. Set model east/north/height offsets in metres, rotation in degrees, scale and up/forward axes, then **Apply alignment preview**. These controls move the mesh only; they do not move spaces or roads or change simulation decisions. All selected models use the same transform.
5. Check the visual-inspection box and choose **Use this environment**. Simulation and comparison controls remain disabled until the preview is confirmed or cancelled. Confirmation records user inspection, not survey accuracy or field validation.
6. Download the environment configuration and retain its original GLBs. Import those files together to restore the same configuration and alignment. Model checksums prevent silently substituting another file.

Imports remain in the current browser tab. PANDA does not upload them to Vercel, add them to GitHub, or retain them after the tab is closed. Downloaded JSON contains geometry, restrictions, alignment and model filenames/checksums; it does not embed GLB binaries. Local files cannot reserve a space or change the published study results.

## Lot JSON contract

Schema version 2 accepts 1–64 fixed destinations and 1–64 entries and 1–64 exits. `destinations` is the generic location list. The legacy `walmart_doors` key remains supported and is generated as an adapter for existing rendering and population code; if both are supplied they must agree. Entry and exit lists may differ. Shared IDs identify the same coordinate. Networks may be directed; supplied directed edges determine legal travel. Explicit forbidden turns and fixed signal/stop controls are supported.

- `meta`: `lot_name`, geographic origin `ref_lat` and `ref_lon`. Local x is east and y is north, in metres. Coordinates must be in a common flat local frame; meshes should be exported in metres.
- `slots`: 2–2,000 records with unique `id`, a `module`, `local_x_m`, `local_y_m` and optional Boolean `is_accessible`, `is_reserved`, `is_unavailable`, `is_blocked` flags. At least one space must be usable. `type` and `price_per_hour` use the existing parking-space loader. Optional `length_m`, `width_m`, `heading_deg` set the displayed space shape; they do not add a vehicle-clearance model.
- `destinations` (or legacy `walmart_doors`): fixed destination records. This historical key is retained for compatibility and does not limit the facility to a Walmart. Each record has `id`, `local_x_m`, `local_y_m`.
- `entry_points` and `exit_points`: paired vehicle access records, using the same coordinate fields. Latitude/longitude values are derived from the local frame on import. Supplied distance fields are replaced by recalculated straight-line distances.
- `aisle_network.nodes`: object mapping node IDs to `[east_m, north_m]`.
- `aisle_network.edges`: pairs of node IDs defining roads (undirected by default; ordered arcs when `directed=true`). Use intermediate nodes for bends and junctions. Crossings must share a node if vehicles can transfer between roads there.
- `aisle_network.aisles`: aisle IDs mapped to two endpoint node IDs. These define exploration targets and aisle-information groups.
- `aisle_network.space_access`: every space ID mapped to `{"node":"road_node_id","aisle":"aisle_id"}`. The engine connects the space centre to that road node with an approach spur. Put the node at the intended approach position and check the spur visually.
- `aisle_network.access_nodes`: every configured access ID mapped to a road node ID. Access positions are connected to those nodes.

The downloadable environment wrapper contains `config`, `alignment` and `model_files`, plus validation/provenance fields. A plain lot JSON is accepted with identity model alignment. Invalid JSON, missing assignments, duplicate centres, invalid transforms and disconnected graphs are rejected. Connectivity does not establish realistic lane widths, parking orientation, collision clearance, building avoidance or traffic calibration. All roads are currently undirected.

## Reproducibility and checks

The original Walmart path retains the original loader, inferred aisle network and decision RNG namespaces. The synthetic environment exports the existing transfer facility's network and restrictions. Imported configurations use explicit networks through the same navigation interface; the utility, search, claim and traffic mechanisms are shared.

Saved runs include the complete environment and alignment in settings, geometry and environment SHA-256 values, and model file checksums. Matched comparisons store the full environment once in top-level settings; individual simulations refer to its checksum to avoid duplicating large JSON configurations. The Python execution side revalidates imported geometry. The research-results tab always displays archived Walmart results; it is not relabeled when another environment is selected.

Run `python -m pytest tests/test_environments.py tests/test_simulation_windows.py tests/test_supply_traffic.py tests/test_cesium_replay.py tests/test_public_platform.py` to check environment rejection, transfer routes, dynamic inventory, live/recorded consistency and existing platform behavior.

## Ready-to-import downtown example

Select **Downtown Laramie · synthetic** to experiment directly. Its approximate origin is 41.3105, -105.5950. Local metre coordinates, driving routes and restrictions retain the synthetic transfer design; translating the geographic anchor does not change local approach, walking or exit distances.

The import panel includes **Download downtown test environment (ZIP)**. Extract it and select `environment.json` plus `synthetic_pavement.glb` in the importer. The JSON records the GLB checksum and identity alignment. This pair can be used to check import, alignment, occupancy selection and simulation without preparing any assets yourself.

## Two Walmart simulation options

**Walmart · original estimate (1,315)** remains the default, using `data/lot_config.json`: 1,315 records, 1,106 usable spaces and 34 accessible designations. Its bytes and archived research outcomes have not been replaced.

**Walmart · satellite estimate (472)** uses `data/lot_config.satellite_estimated.json`: 472 provisional row-fitted bay records, 396 usable and 7 accessible designations under an explicit nearest-original-rule assumption. Each candidate inherits the type, accessibility, reservation, price, unavailable and blocked fields of its nearest original record. These labels are not verified from the imagery. Excluded merchandise/service areas have not been invented as regular parking spaces. This is an exploratory alternative geometry and inventory, not an empirically validated replacement. Walking constraints, references, occupancy and approach routes are evaluated against its own inventory.

The satellite option has its own connected aisle graph, bay angles, distances, configuration hash and saved results. It reuses the original approximate building/pavement context; no fit residual is claimed for that context against the new bays. Space IDs differ between the layouts; compare aggregate outcomes or matched driver records, not same-space IDs across layouts. Changing layouts also changes supply and inherited restriction coverage, so differences cannot be attributed only to rotation or geometry. Do not relabel original paper results as satellite-layout results.

The 5 November review candidate and preserved configuration remain in `research/alignment_review/20261105/`. They are not modified by activating this separate variant. `scripts/build_satellite_environment.py` documents how the runtime variant was derived. The public asset builder reads the standalone data file and does not require the review image archive to deploy.


## Downtown Laramie environment

The selector includes **Downtown Laramie · streets and parking**: 241 provisional space centres, including 199 street spaces and 42 off-street spaces, eight assumed building-front destinations and six boundary access points. These are digitized row estimates, not verified capacity. Some curb segments and loading/accessibility designations remain unclassified. The earlier synthetic transfer layout is retained separately for reproducibility.

`time_limit_minutes` is optional per space. A configured limit excludes spaces when planned activity plus both straight-line walks at the modeled walking speed exceed the limit. It does not simulate fines, enforcement schedules, overstaying or relocation. Missing limits mean no modeled limit, not verified permission to park indefinitely. Downtown street limits are provisionally 120 minutes based on district guidance; sign-level boundaries and enforcement hours require review.

The regular downtown configuration is `data/lot_config.downtown_laramie.json` and starts simulations directly. The earlier `.review.json` remains an archived draft; generic imports marked `meta.review_required=true` still remain preview-only. Downtown launch checks are software verification, not new publication experiments. Inspect `research/downtown_review/20261105/layout_review.html` and the annotated PNG before revising the JSON. The downtown graph now uses mapped First Street one-way directions and five mapped signal locations, with assumed fixed timings. Through traffic is available as an assumed demand scenario. The downtown environment now has a pedestrian network; historical configurations retain straight-line walking. None of these changes establishes field-validated congestion or pedestrian-route predictions.


## Urban experiment controls

Activity profiles are short (15–60 min), near-limit (90–120 min), long (150–240 min), or a mixture with equal group probabilities. These are activity durations, not named driver personas. A separate random stream retains the same trip attributes across matched policies and decision models. The original baseline generator remains unchanged when the baseline profile is selected.

Time-limit policies retain configured limits, remove limits as a counterfactual, or impose 120 minutes on classified on-street spaces. Supply closures remain separate controls. Demand can follow a fixed population or continue for 1–6 hours, deriving the driver count from the arrival gap (maximum 1,200 parking drivers). Observation supports up to six hours. The fixed-window output identifies unfinished trips; it does not force departure or abandonment at the cutoff.

Through traffic uses assumed rates of 30, 120 or 240 vehicles/hour over the selected demand period. Vehicles travel between different randomly selected boundary points on directed routes, share following, junction and signal constraints, and never claim parking. Their IDs begin with `T`; parking-driver IDs begin with `D`. Parking denominators exclude through vehicles; traffic-delay and jam records include both, with a separate through-traffic summary. These rates and uniformly sampled boundaries are sensitivity assumptions, not measured traffic counts.

`aisle_network.controls` accepts `signal` records (node, cycle_s, offset_s, east_west_green and north_south_green intervals) or `stop` records (node and dwell_s). Downtown signals use an assumed 96-s cycle with separate 42-s axis greens and clearance intervals. `turn_restrictions` lists forbidden three-node movements. No downtown turn bans are inferred from absence of source data. Existing geometric junction yielding remains an approximation, not a calibrated intersection model.

The downtown GLB contains 88 OSM building footprints with illustrative heights. It provides visual context only, without vehicle-body collision or visibility effects; matching building footprints now constrain downtown pedestrian routes. Downtown is directly executable from the environment selector. No review approval button is required. The stored review snapshot and historical paper experiments remain unchanged.

Initially parked vehicles can retain the static baseline or depart after assumed residual stays. Residual stays use the selected activity-duration distribution and an independent seeded uniform remaining fraction, capped by each space time limit. They are not sampled from an empirically estimated equilibrium occupancy distribution. Releases are exogenous supply events; they do not add outbound vehicles to traffic. The planned downtown policy grid selects residual departures.

## Geometry audit

Downtown headings explicitly use `heading_reference=clockwise_from_north`; legacy environments retain counterclockwise-from-east headings. Bay polygons and parked-car poses share the same conversion. The downtown off-street count is incomplete: the 42 fitted bays do not represent verified lot capacity. The numbered audit and per-row inventory are in `research/downtown_geometry_audit_20261105/`. Unresolved arrangements are recorded separately, without inventing active spaces.


## Pedestrian network

The active downtown JSON includes `pedestrian_network`: local-metre nodes, typed edges, bay access connectors and exterior destination nodes. `sidewalk`, `shared_lot` and `crossing` edges retain mapped/estimated provenance. Common edges cannot intersect a building or any parking bay. A bay connector may traverse its own bay only, never another bay or building. Roads are crossed only on declared crossing links. Disconnected spaces/destinations have null access and are excluded; no straight-line fallback is permitted when a network is present.

OSM mapped paths are filtered for scope, access and grade. Estimated sidewalk ribbons, lot circulation links and crossing locations complete gaps, with source labels. Stairs and grade-separated features are excluded from this flat draft; wheelchair suitability is not established. Entrances are estimated exterior access points rather than verified doors. Existing bay-geometry conflicts and missing corridors currently reduce reachable parking supply; see the generated report.

Routing distances are used for candidate utility in M0/M1/CPT, walking constraints, legal-inventory references, expected time-limit compatibility, walking duration and animation. Route distances use a 1-m mesh. Pedestrians traverse those paths at the walking speed and record stationary waiting intervals. Configured crossings require traffic interactions. Admission uses a conservative gap check, with vehicle yielding while a crossing is occupied and additional clearance checks in shared areas. This is a kinematic approximation, not a calibrated pedestrian gap-acceptance or rigid-body collision model.

Run `python scripts/build_downtown_pedestrians.py` after rebuilding downtown geometry/context. Shapely 2.2.0 is a build-only dependency; runtime uses the existing NetworkX dependency. `python scripts/verify_downtown_pedestrians.py` performs native route-integrity checks. Preview and reports are under `research/downtown_pedestrians_20261105/`. Historical Walmart/synthetic configurations and archived paper results retain their original walking assumptions. New comparisons need to use the same network version across matched conditions.
