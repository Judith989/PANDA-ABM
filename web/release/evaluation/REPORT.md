# Platform implementation evaluation

This record separates computational implementation tests from the 3,400
behavioral study trials. It does not add a user study or field validation.

## Correctness and provenance

- All 18 native/browser fixtures passed. They used three
  drivers, each primary decision model, all three information conditions and
  80%/95% initial occupancy. Population and occupied-space hashes matched exactly.
- An independent exported comparison covered 18 scenarios,
  two seeds, all three models and 72 driver-scenario
  records. Every individual outcome and aggregate paired estimate matched native
  execution, with an absolute numerical tolerance of 1e-8.
- Current native CPT outcomes for 80 drivers, seed 1000 and 80% occupancy matched
  final TCSS archive signatures under all three information conditions. The saved
  website reference was refreshed to the final-study version; the earlier replay
  used an older CPT implementation. Source differences are retained in its
  verification metadata, so outcome agreement is not called source identity.
- The worker verifies the Python source archive against its manifest before
  execution. Exports retain the manifest actually loaded by that worker.

Full-size release verification additionally covered 9
scenarios and 720 driver-scenario
records against the final archive. Numerical population attributes were checked
at 1e-12 absolute tolerance; the maximum difference was
5.684341886080802e-14. Raw population
hashes need not match across runtimes when floating-point representations differ.
Within each matched comparison, input hashes must match exactly across arms.

## Timing protocol

Native and browser tests were conducted sequentially, with no simultaneous
native simulation test workload during the final browser measurement. Each
platform completed full arrival-to-departure/abandonment lifecycles for CPT,
space information, 80% occupancy, 20-second arrivals and seeds 7000–7002.
Driver counts were 20, 80 and 120; each size therefore has three observations.
Native timing includes model/population initialization and completion. Browser
request latency additionally includes worker scheduling, JSON serialization
and result transfer. Runtime loading is excluded from those request timings.

The embedded Chromium browser reported 16 logical
processors. Its viewport was 1401 by 985 CSS pixels,
with device-pixel ratio 0.91. The native system was
Windows-11-10.0.26200-SP0. Full user-agent, processor and package strings remain in the raw
JSON. Browser runtime initialization took
8.26 s in this session; browser
caches were uncontrolled, so this is not a cold-network-load estimate.

| Drivers | Native median (s) | Browser median (s) | Browser range (s) |
|---:|---:|---:|---:|
| 20 | 3.50 | 4.42 | 4.40–4.62 |
| 80 | 9.05 | 12.73 | 11.95–12.90 |
| 120 | 12.67 | 17.45 | 16.69–17.91 |

Display measurements used the fixed stationary Cesium scene, with the saved
80-driver replay paused at time zero. The worker's simulated population varied;
the rendered scene did not vary with that population. Across the nine requests,
the largest within-request 95th-percentile animation-frame interval was
1016.30 ms. Actual Cesium post-render counts are also recorded. The final
embedded-browser capture exhibited an approximately one-second frame cadence
despite the Page Visibility flag reporting true. Those frame timings cannot
establish active-window animation throughput. An earlier diagnostic capture
had a 16.8-ms frame interval; it is retained separately and is not pooled with
the final timing dataset. Browser request latency is conditional on the
observed render state, so these data do not isolate interpreter overhead.
These values do not measure frame rate for 120 animated vehicles. Live simulation, pause,
matched comparisons, cancellation and JSON export were checked separately.

## Interpretation and reproducibility

The results support browser-side execution of the unchanged parking decision
logic and successful end-user controls on this device. They do not
establish cloud concurrency, performance on other devices, empirical behavioral
accuracy, or end-user usability. A controlled multi-device study and a user study
remain distinct possible evaluations.

Run `python scripts/benchmark_public_platform.py` for native fixtures/timings.
Run the website's performance test with a visible tab and a recorded viewport.
Download its measurements as `browser_performance.json`, then run
`python scripts/report_platform_evaluation.py`. Use
`python scripts/verify_platform_comparison.py` with the exported comparison
for the independent paired-output check. Do not run native and browser
computational benchmarks concurrently.
