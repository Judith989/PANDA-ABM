"""Refresh web/release after simulation, data or interface changes, from a fresh clone.

build_public_platform.py regenerates everything but needs private study archives
(results/, paper/, replays). This script only updates what source edits affect:
the Python bundle (project files replaced; pinned mesa/networkx/tqdm entries kept
byte-for-byte), the downtown entry of environments.json, and the manifest
checksums that web/build.mjs verifies. Saved study results and the reference
replay are left untouched.
"""
from pathlib import Path
import hashlib
import io
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT/'web/release'
sys.path.insert(0, str(ROOT))
sha = lambda data: hashlib.sha256(data).hexdigest()


def project_files():
    files = {p.relative_to(ROOT).as_posix(): p for p in sorted((ROOT/'panda_abm').rglob('*.py'))}
    for name in ('lot_config.json', 'lot_config.synthetic.json', 'lot_config.satellite_estimated.json',
                 'lot_config.downtown_laramie.review.json', 'lot_config.downtown_laramie.json', 'lot_config.corrected_imagery.json'):
        files['data/'+name] = ROOT/'data'/name
    return files


def main():
    manifest_path = RELEASE/'engine/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    files = project_files()
    old = zipfile.ZipFile(RELEASE/'engine/python-source.zip')
    kept = [i for i in old.infolist() if not i.filename.startswith(('panda_abm/', 'data/'))]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        entries = {i.filename: old.read(i) for i in kept}
        entries.update({name: path.read_bytes() for name, path in files.items()})
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[name])
    (RELEASE/'engine/python-source.zip').write_bytes(buffer.getvalue())

    from panda_abm.twin.environments import corrected_environment, downtown_environment, validate_environment
    environments = json.loads((RELEASE/'environments.json').read_text(encoding='utf-8'))
    environments['downtown'] = downtown_environment()
    # The corrected layout reuses the Walmart building and pavement models and their alignment.
    corrected = corrected_environment()
    corrected.update(alignment=environments['satellite']['alignment'], model_files=environments['satellite']['model_files'])
    environments['corrected'] = validate_environment(corrected)
    (RELEASE/'environments.json').write_text(json.dumps(environments, separators=(',', ':'), allow_nan=False), encoding='utf-8')

    manifest['source_sha256'] = {name: sha(path.read_bytes()) for name, path in files.items()}
    manifest['bundle_sha256'] = sha(buffer.getvalue())
    manifest['interface_sha256'] = {name: sha((ROOT/'dashboard'/name).read_bytes()) for name in manifest['interface_sha256']}
    manifest['environment_assets_sha256'] = {name: sha((RELEASE/name).read_bytes()) for name in manifest['environment_assets_sha256']}
    manifest_path.write_text(json.dumps(manifest, separators=(',', ':')), encoding='utf-8')
    print(json.dumps(dict(bundle_sha256=manifest['bundle_sha256'], project_files=len(files), dependency_files=len(kept))))


if __name__ == '__main__':
    main()
