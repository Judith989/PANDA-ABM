# PANDA Parking Simulation Lab

The public platform combines a Cesium 3D scene, interactive simulations,
matched information comparisons and saved study results. The original Python
ABM executes in a Pyodide Web Worker on the visitor's device. The website
changes how experiments are requested and displayed; it does not rewrite
parking decisions in JavaScript.

## End-user workflow

1. **3D simulation:** choose deterministic utility, stochastic utility or CPT;
   choose information, occupancy, arrivals, driver count and seed. Start a live
   simulation or compute a complete replay. Inspect drivers and spaces, switch
   between 3D and north-up views, and download the replay or a scene image.
2. **Matched comparisons:** choose one to three models and 1–30 replications.
   All three information conditions use the same generated population and
   initial occupancy for each seed. The platform checks matching fingerprints.
   Download driver outcomes and provenance as JSON, or aggregate estimates as CSV.
3. **Study results:** inspect the saved primary 30-replication experiments.
   These summaries retain their own provenance and are separate from new trials.
4. **About & performance:** read assumptions and run device-side verification
   and performance tests. Download the measurements for independent analysis.

Search and success metrics include every arrival. Walking and intended-exit
proximity include parked drivers. Paired combined-time differences include only
those parked in both conditions and use a walking speed of 1.4 m/s. Intervals
resample whole matched replications 10,000 times; they are exploratory pointwise
95% percentile intervals with no multiplicity correction. One replication does
not produce an uncertainty interval. Runs are held in the tab's memory; download
results before closing it. At most four newly computed replays are retained.

## Reproduce the local website

Install the repository requirements. The release was prepared with Mesa 3.5.1,
NetworkX 3.7 and tqdm 4.70.1. Scientific browser wheels come from Pyodide 314.0.7.
Browser and native Python/NumPy versions differ and are recorded in exports.
From the repository root:

```powershell
python scripts/download_browser_runtime.py
python scripts/build_public_platform.py
python scripts/benchmark_public_platform.py --fixtures-only
python -m http.server 8765 --bind 127.0.0.1 --directory dashboard
```

Open http://127.0.0.1:8765/. CesiumJS and OpenStreetMap need internet access.
The Python runtime and scientific wheels are served from the site's own assets.
The build requires the prepared GLBs and reference replay. If they are absent,
prepare them from the user's original model directory:

```powershell
python scripts/prepare_cesium_assets.py --source C:/Users/jnjoku/Documents/ABM-Parking
python scripts/serve_dashboard.py --prepare-replay
```

The legacy loopback server remains a developer API/replay utility. The public
browser interface uses its worker engine and does not need that Python server.

## Implementation and reproducibility

- `dashboard/app.js` renders corrected space coordinates, movement and occupancy.
- `dashboard/platform.js` manages end-user workflows, exports and browser tests.
- `dashboard/engine/client.js` manages worker requests and cancellation.
- `dashboard/engine/worker.js` loads the Python source and invokes existing
  replay/live functions or the comparison adapter.
- `panda_abm/twin/platform.py` completes trips and summarizes paired comparisons.
  Decision, search, movement and occupancy rules remain in the existing model.
- `scripts/build_public_platform.py` copies an explicit public-file allowlist,
  bundles source and dependency licenses, and records source/runtime hashes.
- `scripts/benchmark_public_platform.py` creates native verification fixtures
  and repeated full-lifecycle timings for 20, 80 and 120 drivers.
- `scripts/verify_platform_comparison.py` checks a browser-exported comparison
  against native execution, including every driver and paired estimates.
- `paper/platform_evaluation/` contains the evaluation protocol and evidence.

For native measurements run `python scripts/benchmark_public_platform.py`.
For browser measurements use the performance button while keeping the tab
visible. Record viewport and software versions. Run native and browser timing
experiments sequentially to avoid competing test workloads. Device measurements
do not establish server capacity, mobile performance, field accuracy or usability.

## Geometry and scope

The estimated configuration contains 1,315 records, 1,106 usable spaces and
34 accessible designations. Corrected JSON coordinates determine simulated
space positions, doors and vehicle accesses. Building and pavement GLBs are
approximate context: the retained similarity fit has 3.240 m RMS residual and
13.135 m maximum residual. The GLBs use explicit Y-up/X-forward loading to match
that transform. `dashboard/alignment.json` records the fit and config hash.

The platform supports scenario-based decision support. It does not continuously
assimilate observed occupancy or validate assumed behavior against field data.
See `THIRD_PARTY.md` for dependencies and map attribution.
