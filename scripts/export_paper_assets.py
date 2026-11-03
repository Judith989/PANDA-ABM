"""Copy a small verified information-study evidence set outside ignored results/.

Does not rerun simulations, modify original archives or stage/commit Git files.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
FILES=(
    'information_comparison.png','spatial_choices.png','summary.csv','contrasts.csv',
    'individual_choices.csv','target_competition.csv','mobility_outcomes.csv',
    'door_access_outcomes.csv','requirements-pinned.txt','design.json',
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'results/parking_information_20261028')
    parser.add_argument('--output',type=Path,default=ROOT/'research/paper_assets/parking_information_20261028')
    args=parser.parse_args();source=args.source.resolve();out=args.output.resolve()
    manifest=json.loads((source/'bundle_manifest.json').read_text())
    # Validate every selected source before writing any copied artifact.
    for name in FILES:
        if sha256(source/name)!=manifest[name]:raise ValueError(f'Source checksum mismatch: {name}')
    out.mkdir(parents=True,exist_ok=True)
    artifacts={}
    for name in FILES:
        shutil.copyfile(source/name,out/name)
        assert sha256(out/name)==manifest[name]
        artifacts[name]=dict(sha256=manifest[name],bytes=(out/name).stat().st_size)
    plan=json.loads((source/'design.json').read_text())
    provenance=dict(study='Current parking information, 2026-10-28',runs=plan['runs'],
        source_directory=source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else str(source),
        original_bundle_sha256=sha256(source/'reproducibility_bundle.zip'),
        original_manifest_sha256=sha256(source/'bundle_manifest.json'),
        frozen_source_snapshot_sha256=sha256(source/'source_snapshot.zip'),
        artifacts=artifacts,
        note='Exact selected copies; original raw/archive files remain unchanged and Git-ignored. These figures/tables are working paper assets, not a finalized manuscript. No data or analysis is recomputed.')
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    readme='''# Parking information: working paper assets

Study completed 28 October 2026: 270 matched simulations, 21,600 driver outcomes,
ten seeds, three occupancy levels, three decision models and three information
conditions. This folder contains exact copies of selected verified outputs for
version control and manuscript preparation. It does not replace the full archive.

## Figures

| File | Suggested role and caption |
|---|---|
| [information_comparison.png](information_comparison.png) | Figure 1. Mean search for all arrivals, walking among parked drivers and success across information conditions, M0/M1/CPT and 40%/80%/95% initial occupancy. Error bars are 95% seed-bootstrap intervals for condition means. Use paired contrasts to assess differences; interval overlap alone is not a paired comparison. |
| [spatial_choices.png](spatial_choices.png) | Figure 2. CPT parking selections at 40% initial occupancy on estimated lot geometry. The shared color scale counts parkings per stall across ten replications. Stars mark Door 1/2; triangles mark Entry/Exit A/B. Counts can include stall reuse. This is one descriptive scenario, not all models or observed real behavior. |

## Tables and source definitions

| File | Contents / paper use |
|---|---|
| [design.json](design.json) | Settings and frozen source hashes; basis for a methods/scenario table |
| [summary.csv](summary.csv) | 27 model/occupancy/information cells; basis for the principal outcome table |
| [contrasts.csv](contrasts.csv) | Paired intervention-minus-control effects by model and occupancy, with 95% seed-bootstrap intervals |
| [individual_choices.csv](individual_choices.csv) | Same-space/aisle fractions, paired walking/search changes among jointly parked drivers, and success switches |
| [target_competition.csv](target_competition.csv) | Per-replication target selections, selections of already-pursued stalls and peak concurrent targeters |
| [mobility_outcomes.csv](mobility_outcomes.csv) | Descriptive breakdown by physical mobility limitation |
| [door_access_outcomes.csv](door_access_outcomes.csv) | Descriptive breakdown by destination door, arrival access and intended exit |
| [requirements-pinned.txt](requirements-pinned.txt) | Exact study dependency versions; Python version is in design.json |
| [provenance.json](provenance.json) | Artifact checksums, sizes and original archive/source snapshot checksums |

Occupancy is a fraction (0.40, 0.80, 0.95); success and same-choice fields are
fractions, not percentages. Times are seconds and distances meters. Summary
means are equal-weight replication means. Each main cell has ten replications
of 80 drivers. Failed claims and remote targets count events, including repeated
events by the same driver. In contrasts.csv, negative search/walk differences
mean a smaller outcome under the intervention; positive success differences
mean a higher parking rate. Success deltas are fractions, so multiply by 100
to express percentage-point changes.

Walking averages exclude unparked drivers. Jointly parked comparisons use a
selected matched cohort and must not be interpreted as effects on all arrivals.
Small subgroup tables are exploratory. Interacting drivers are not independent
replicates. Detailed information can change approach/walking tradeoffs and
competition; the results concern the implemented use rules, not universal
benefits of information. No personas were assigned in the primary population.

## Provenance and reproduction

The original study is in results/parking_information_20261028/ at the repository
root. Its REPORT.md contains the full interpretation and limitations; its
reproducibility_bundle.zip includes raw outcomes, selected events, population
files, occupied-ID files and archived source. That folder is Git-ignored.
The original experiment/source archives have not been rewritten to match later
README edits. Archive checksums in provenance.json identify the exact evidence.

To refresh these exact copies after a verified source study exists:

```powershell
python scripts/export_paper_assets.py
```

The exporter validates source hashes before copying and does not rerun the study.
For simulation/report commands, see [the root README](../../../README.md).
Keep the full archive in durable storage or a publication/release attachment;
this curated folder alone cannot reproduce all raw decisions. Its manuscript
tables, figure numbering and captions remain provisional.
'''
    (out/'README.md').write_text(readme,encoding='utf-8')
    print(f'Exported {len(FILES)} verified artifacts to {out}')


if __name__=='__main__':main()
