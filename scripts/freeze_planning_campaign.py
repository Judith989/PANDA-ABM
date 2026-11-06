"""Create a new immutable-input campaign without touching older result packages."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():raise SystemExit('Use a new campaign directory; existing results are never overwritten.')
    frozen=out/'frozen_source';frozen.mkdir(parents=True)
    files=[]
    for folder in ('panda_abm','scripts','tests'):
        files.extend((ROOT/folder).rglob('*.py'))
    files.extend((ROOT/'data').glob('*.json'))
    files.extend(ROOT.glob('*requirements*.txt'))
    files.append(ROOT/'dashboard/assets/downtown_buildings.glb')
    manifest={}
    for source in sorted(set(files)):
        relative=source.relative_to(ROOT);target=frozen/relative
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        manifest[relative.as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    versions={}
    for package in ('numpy','scipy','networkx','mesa','pandas','scikit-learn','matplotlib'):
        try:versions[package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:versions[package]=None
    payload=dict(files=manifest,python=platform.python_version(),dependencies=versions,
        study='Corrected network walking and traffic planning campaign',
        primary_environments=['walmart_satellite','downtown'],
        geometry_controls=['walmart_original','synthetic'],
        old_results='Preserved separately; no reuse of earlier outcomes',
        presentation='All results belong to the main results package; no supplementary results directory')
    (out/'source_manifest.json').write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
    (out/'README.md').write_text('''# Corrected planning campaign

This is a new experiment version. Earlier results and the stopped 20261105
campaign remain separate and are not inputs to the numerical comparisons.

The satellite-estimated Walmart and estimated downtown environments are the
primary physical cases. Original Walmart and the synthetic layout test geometry
sensitivity. Neither real-site reconstruction is surveyed or field-calibrated.

Run the runner inside frozen_source, passing this directory as --output. It
checks source hashes and refuses checkpoints from another version. status.json
must show finished=true and failed=0 before these results are called complete.

Every condition and contrast is retained in the main results package. The
figures, tables and results text are not supplementary material. Raw individual
records provide the reproducibility trail; they are not a second set of findings.
''',encoding='utf8')
    print(out)

if __name__=='__main__':main()
