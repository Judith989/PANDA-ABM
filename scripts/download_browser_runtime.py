"""Fetch pinned official Pyodide files; verify all scientific wheels."""
from pathlib import Path
import hashlib
import json
import urllib.request

VERSION='314.0.7'
BASE=f'https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/'
OUT=Path(__file__).resolve().parents[1]/'dashboard/engine/runtime'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    def fetch(name,expected=None):
        path=OUT/name
        if path.exists() and (expected is None or hashlib.sha256(path.read_bytes()).hexdigest()==expected):return path
        data=urllib.request.urlopen(BASE+name,timeout=120).read()
        if expected and hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError(f'Checksum failed: {name}')
        path.write_bytes(data);print(f'{name}: {len(data)} bytes',flush=True);return path
    for name in ('pyodide.mjs','pyodide.asm.mjs','pyodide.asm.wasm','python_stdlib.zip','pyodide-lock.json'):
        fetch(name)
    lock=json.loads((OUT/'pyodide-lock.json').read_text());seen=set()
    def package(name):
        if name in seen:return
        seen.add(name);entry=lock['packages'][name]
        for dependency in entry.get('depends',[]):package(dependency)
        fetch(entry['file_name'],entry['sha256'])
    for name in ('numpy','pandas','scipy'):package(name)
    license_path=OUT/'LICENSE-PYODIDE.txt'
    if not license_path.exists():license_path.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/pyodide/pyodide/main/LICENSE',timeout=30).read())


if __name__=='__main__':main()
