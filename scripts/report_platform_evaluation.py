"""Produce the platform table and implementation record from measured evidence."""
from pathlib import Path
import csv
import hashlib
import json
import statistics

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/'paper/platform_evaluation'
    browser=json.loads((folder/'browser_performance.json').read_text())
    native=json.loads((folder/'native_performance.json').read_text())
    paired=json.loads((folder/'matched_comparison_verification.json').read_text())
    archived=json.loads((folder/'archived_reference_verification.json').read_text())
    full=json.loads((folder/'full_size_verification.json').read_text()) if (folder/'full_size_verification.json').exists() else None
    assert browser['status']=='passed' and len(browser['timings'])==9
    assert all(r['passed'] for r in browser['fixtures']) and paired['passed']
    assert all(r['visible_during_measurement'] for r in browser['timings'])
    assert all(r['outcome_signature_matches'] for r in archived['cases'])
    if full:assert full['passed']
    rows=[]
    for size in (20,80,120):
        b=[r for r in browser['timings'] if r['population']==size]
        n=[r for r in native['timings'] if r['population']==size]
        rows.append(dict(drivers=size,repetitions=3,native_median_s=statistics.median(r['wall_s'] for r in n),
            native_min_s=min(r['wall_s'] for r in n),native_max_s=max(r['wall_s'] for r in n),
            browser_median_s=statistics.median(r['request_ms']/1000 for r in b),
            browser_min_s=min(r['request_ms']/1000 for r in b),browser_max_s=max(r['request_ms']/1000 for r in b),
            worst_frame_p95_ms=max(r['raf_p95_ms'] for r in b)))
    with (folder/'performance_summary.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    table=r'''\begin{table}[!t]
\caption{Median platform execution time (s).}
\label{platform_timing}
\centering
\begin{tabular}{rrr}
\toprule
Drivers & Native Python & Browser request \\
\midrule
'''+ '\n'.join(f"{r['drivers']} & {r['native_median_s']:.2f} & {r['browser_median_s']:.2f} "+r'\\' for r in rows)+r'''
\bottomrule
\end{tabular}
\end{table}
'''
    (ROOT/'paper/current_manuscript/platform_performance_table.tex').write_text(table,encoding='utf-8')
    viewport=browser['viewport'];worst=max(r['worst_frame_p95_ms'] for r in rows)
    text=f'''# Platform implementation evaluation

This record separates computational implementation tests from the 3,400
behavioral study trials. It does not add a user study or field validation.

## Correctness and provenance

- All {len(browser['fixtures'])} native/browser fixtures passed. They used three
  drivers, each primary decision model, all three information conditions and
  80%/95% initial occupancy. Population and occupied-space hashes matched exactly.
- An independent exported comparison covered {paired['scenarios']} scenarios,
  two seeds, all three models and {paired['driver_scenario_records']} driver-scenario
  records. Every individual outcome and aggregate paired estimate matched native
  execution, with an absolute numerical tolerance of 1e-8.
- Current native CPT outcomes for 80 drivers, seed 1000 and 80% occupancy matched
  final TCSS archive signatures under all three information conditions. The saved
  website reference was refreshed to the final-study version; the earlier replay
  used an older CPT implementation. Source differences are retained in its
  verification metadata, so outcome agreement is not called source identity.
- The worker verifies the Python source archive against its manifest before
  execution. Exports retain the manifest actually loaded by that worker.

Full-size release verification additionally covered {full['scenarios'] if full else 'pending'}
scenarios and {full['driver_scenario_records'] if full else 'pending'} driver-scenario
records against the final archive. Numerical population attributes were checked
at 1e-12 absolute tolerance; the maximum difference was
{full['max_absolute_population_difference'] if full else 'pending'}. Raw population
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

The embedded Chromium browser reported {browser['logical_processors']} logical
processors. Its viewport was {viewport['width']} by {viewport['height']} CSS pixels,
with device-pixel ratio {viewport['device_pixel_ratio']:.2f}. The native system was
{native['os']}. Full user-agent, processor and package strings remain in the raw
JSON. Browser runtime initialization took
{browser['initialization']['initialize_ms']/1000:.2f} s in this session; browser
caches were uncontrolled, so this is not a cold-network-load estimate.

| Drivers | Native median (s) | Browser median (s) | Browser range (s) |
|---:|---:|---:|---:|
'''+ '\n'.join(f"| {r['drivers']} | {r['native_median_s']:.2f} | {r['browser_median_s']:.2f} | {r['browser_min_s']:.2f}–{r['browser_max_s']:.2f} |" for r in rows)+f'''

Display measurements used the fixed stationary Cesium scene, with the saved
80-driver replay paused at time zero. The worker's simulated population varied;
the rendered scene did not vary with that population. Across the nine requests,
the largest within-request 95th-percentile animation-frame interval was
{worst:.2f} ms. Actual Cesium post-render counts are also recorded. The final
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
'''
    (folder/'REPORT.md').write_text(text,encoding='utf-8')
    evidence=['browser_performance.json','native_performance.json','matched_comparison_verification.json','archived_reference_verification.json']
    if full:evidence.append('full_size_verification.json')
    (folder/'evidence_sha256.json').write_text(json.dumps({name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in evidence},indent=2))
    print(json.dumps(dict(rows=rows,worst_frame_p95_ms=worst)))


if __name__=='__main__':main()
