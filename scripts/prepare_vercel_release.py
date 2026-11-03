"""Snapshot tested public assets for a GitHub-to-Vercel build without raw study data."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/'dashboard'
DEST=ROOT/'web/release'


def main():
    files=['scene.json','reference.json','study-results.json','alignment.json',
           'assets/walmart_building.glb','assets/parking_asphalt.glb',
           'engine/manifest.json','engine/python-source.zip','engine/native-fixtures.json',
           'engine/full-size-fixture.json','engine/runtime/LICENSE-PYODIDE.txt']
    files += ['evaluation/'+name for name in ('REPORT.md','performance_summary.csv',
        'browser_performance.json','native_performance.json','matched_comparison_verification.json',
        'archived_reference_verification.json','full_size_verification.json')]
    manifest=json.loads((WEB/'engine/manifest.json').read_text())
    for name,expected in manifest['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError(f'Source bundle is stale: {name}; rebuild public assets first')
    for name,expected in manifest['interface_sha256'].items():
        if hashlib.sha256((WEB/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError(f'Interface snapshot is stale: {name}; rebuild public assets first')
    for relative in files:
        source=WEB/relative;target=DEST/relative
        if not source.is_file():raise FileNotFoundError(f'Prepare the tested dashboard asset first: {relative}')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    print(json.dumps(dict(files=len(files),bytes=sum((DEST/name).stat().st_size for name in files),
                         bundle_sha256=manifest['bundle_sha256'])))


if __name__=='__main__':main()
