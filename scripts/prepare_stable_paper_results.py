"""Package the completed paper evidence without mixing in development traffic runs."""
from pathlib import Path
import hashlib
import json
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'paper/results_section'
OUT = ROOT / 'paper/stable_results_20261106'


def main():
    if OUT.exists():
        raise SystemExit('Package already exists; preserve it and select a new version.')
    checks = []
    snapshot = ROOT / 'results/tcss_first_batch_20261028/source_snapshot.zip'
    with zipfile.ZipFile(snapshot) as archive:
        original_lot = archive.read('data/lot_config.json')
    for name in ('asset_provenance.json', 'single_column_provenance.json'):
        provenance = json.loads((SOURCE / name).read_text())
        for relative, expected in provenance['source_sha256'].items():
            normalized = relative.replace('\\', '/')
            content = original_lot if normalized == 'data/lot_config.json' else (ROOT / normalized).read_bytes()
            actual = hashlib.sha256(content).hexdigest()
            assert actual == expected, (name, relative, 'source changed')
            checks.append(dict(manifest=name, source=normalized, sha256=actual,
                               archived_configuration=normalized == 'data/lot_config.json'))
    experiment_checks = {}
    for directory in ('tcss_first_batch_20261028', 'tcss_robustness_20261028', 'tcss_numerical80_20261028'):
        path = ROOT / 'results' / directory / 'checks.json'
        if not path.exists():
            continue
        records = json.loads(path.read_text())
        failures = [(i, key) for i, row in enumerate(records) for key, value in row.items()
                    if isinstance(value, bool) and not value]
        assert not failures, (directory, failures)
        experiment_checks[directory] = len(records)
    OUT.mkdir()
    # Preserve all scientific figure options and numeric tables in the main package.
    for folder in ('img', 'figures', 'additional_figures', 'tables', 'source_tables', 'all_driver_profile_analysis'):
        shutil.copytree(SOURCE / folder, OUT / folder)
    for name in ('results.tex', 'results.txt', 'additional_results.tex', 'experimental_design_site.tex',
                 'case_study_figure.tex', 'references.bib', 'claim_checks.json', 'asset_provenance.json',
                 'single_column_provenance.json', 'figure_options.md', 'single_column_figures.md'):
        shutil.copy2(SOURCE / name, OUT / name)
    (OUT / 'experiment_lot_config.json').write_bytes(original_lot)
    text = (OUT / 'results.tex').read_text()
    assets = re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', text)
    assert all((OUT / asset).exists() for asset in assets)
    report = dict(status='passed', new_simulations=0, source_hash_checks=checks,
                  stored_simulation_checks=experiment_checks, results_figure_blocks=len(assets),
                  included_figures=assets, excluded_campaign='final_planning_study_20261105',
                  excluded_development_runs='research/vehicle_clearance_20261105')
    (OUT / 'verification.json').write_text(json.dumps(report, indent=2))
    (OUT / 'README.md').write_text('''# Paper results for joint revision

This package preserves the completed behavioral study and its all-driver response
analysis. It contains existing results, not a rerun of the current dashboard.
The original experiment configuration is experiment_lot_config.json. Source
hashes were checked against the saved provenance; the archived lot configuration
was used instead of the changed live configuration. verification.json records
these checks. Earlier results and the current manuscript were not overwritten.

## Evidence retained

| Question | Evidence for the paper |
| --- | --- |
| RQ1: Driver heterogeneity | Preference controls, walking constraints, all-driver response profiles and information benefits. Candidate groups do not establish a stable persona taxonomy. |
| RQ2: Decision models | Deterministic utility, stochastic utility, CPT, linear-CPT and simple-search comparisons; individual choices and collective outcomes. Linear CPT has no 40% occupancy experiment. |
| RQ3: Information effects | Search, parking success, walking, intended-exit distance, failed claims, information adoption and effects on uninformed drivers. |
| RQ4: Robustness | Behavioral controls, delayed information, background departures, synthetic layout and simulation time steps. |

## Scope to preserve when rewriting

These experiments used the earlier estimated Walmart layout and synthetic
transfer layout, with straight-line walking distances and independent vehicle
movement. Do not describe their results as measured network walking, traffic
queues, downtown policy effects, or outcomes of the updated clearance model.
Parking competition means competing claims on spaces; it is not traffic delay.
The latest Cesium platform can be described as an implementation extension, but
screenshots do not validate its new traffic mechanisms.

Downtown congestion, crossing waits, exact-supply interventions, and the stopped
planning campaign are excluded from numerical findings pending verification.
The new traffic and pedestrian-routing features should be identified as work
in progress, not used to strengthen the completed study's empirical claims.

## Files and next writing step

results.tex and results.txt are preserved working drafts for our joint revision;
their prose has not been declared final. They contain 15 figure blocks. img/
contains the referenced assets; tables/ and source_tables/ contain numeric and
LaTeX tables. Additional figure options and all-driver analysis are included in
this same main results package. No supplementary-results folder was created.

Any inherited wording that promises supplementary material must be removed
during joint revision. Select the necessary evidence for the main paper and
keep the remaining options as working assets, without promising a supplement.
The manuscript's methods and limitations must describe the version that
produced these results. We will revise the necessary sections together.
''', encoding='utf8')
    manifest = {p.relative_to(OUT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in OUT.rglob('*') if p.is_file()}
    (OUT / 'package_manifest.json').write_text(json.dumps(manifest, indent=2))
    destination = shutil.make_archive(str(OUT), 'zip', OUT)
    print(json.dumps(dict(package=str(OUT), zip=destination, figure_blocks=len(assets),
                          hash_checks=len(checks), simulation_checks=experiment_checks)))


if __name__ == '__main__':
    main()
