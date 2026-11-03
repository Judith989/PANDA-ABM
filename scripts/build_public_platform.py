"""Build public assets from an explicit allowlist; never copy private result trees."""
from pathlib import Path
from importlib.metadata import distribution
import argparse
import csv
import gzip
import hashlib
import json
import shutil
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')


def build(destination=None):
    from panda_abm.twin.replay import DEFAULTS
    web=ROOT/'dashboard';engine=web/'engine';engine.mkdir(exist_ok=True)
    files={p.relative_to(ROOT).as_posix():p for p in (ROOT/'panda_abm').rglob('*.py')}
    files['data/lot_config.json']=ROOT/'data/lot_config.json'
    dependencies={}
    for name in ('mesa','tqdm','networkx'):
        dist=distribution(name);base=Path(dist.locate_file(name));dependencies[name]=dist.version
        for p in base.rglob('*'):
            if p.is_file() and (p.suffix in ('.py','.json','.txt') or 'LICENSE' in p.name):
                files[p.relative_to(base.parent).as_posix()]=p
        for item in dist.files or []:
            if any(word in str(item).upper() for word in ('LICENSE','COPYING')):
                p=Path(dist.locate_file(item))
                if p.is_file():files['licenses/'+name+'/'+p.name]=p
    with zipfile.ZipFile(engine/'python-source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name,p in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,p.read_bytes())
    manifest=dict(schema_version=1,pyodide='314.0.7',dependencies=dependencies,
        source_sha256={name:hashlib.sha256(p.read_bytes()).hexdigest() for name,p in sorted(files.items()) if name.startswith(('panda_abm/','data/'))},
        bundle_sha256=hashlib.sha256((engine/'python-source.zip').read_bytes()).hexdigest(),
        runtime_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((engine/'runtime').glob('*')) if p.is_file()},
        interface_sha256={name:hashlib.sha256((web/name).read_bytes()).hexdigest() for name in ('index.html','app.js','platform.js','platform.css','platform-views.html','engine/worker.js','engine/client.js')})
    write_json(engine/'manifest.json',manifest)
    study_root=ROOT/'results/tcss_first_batch_20261028'
    with (study_root/'drivers.csv').open(newline='') as handle:
        selected=[r for r in csv.DictReader(handle) if r['seed']=='1000' and r['occupancy']=='0.8' and r.get('variant','base')=='base' and r['model'] in ('deterministic','rum','cpt')]
    checks=json.loads((study_root/'checks.json').read_text());reference_runs=[]
    for model in ('deterministic','rum','cpt'):
        for info in ('unaided','aisle','space'):
            expected=next(c for c in checks if c['seed']==1000 and c['occupancy']==.8 and c['model']==model and c['information']==info and c.get('variant','base')=='base')
            outcomes=[]
            for row in selected:
                if row['model']!=model or row['information']!=info:continue
                result={key:(float(row[key]) if row[key] else None) for key in ('search_s','search_distance_m','walk_m','exit_distance_m','lost_claims','parking_time_s')}
                result.update(driver=row['driver'],success=row['success']=='True',chosen_space=row['chosen_space'] or None);outcomes.append(result)
            reference_runs.append(dict(model=model,information=info,population_sha256=expected['population_sha256'],initial_occupancy_sha256=expected['initial_occupancy_sha256'],outcomes=outcomes))
    write_json(engine/'full-size-fixture.json',dict(population=json.loads((study_root/'core/populations/1000_0.8.json').read_text()),runs=reference_runs,source_csv_sha256=hashlib.sha256((study_root/'drivers.csv').read_bytes()).hexdigest()))
    write_json(web/'scene.json',dict(config=json.loads((ROOT/'data/lot_config.json').read_text()),
        alignment=json.loads((web/'alignment.json').read_text()),defaults=DEFAULTS))
    write_json(web/'reference.json',json.loads(gzip.decompress((web/'replays/baseline.json.gz').read_bytes())))
    def rows(name):
        with (ROOT/'paper/tables/complete'/name).open(newline='',encoding='utf-8') as handle:return list(csv.DictReader(handle))
    study_files=['paper/tables/complete/first_batch_cell_means.csv','paper/tables/complete/first_batch_information_effects.csv','results/tcss_first_batch_20261028/design.json']
    write_json(web/'study-results.json',dict(label='Saved study experiments',replications=30,
        provenance_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in study_files},
        cells=rows('first_batch_cell_means.csv'),effects=rows('first_batch_information_effects.csv')))
    evaluation=web/'evaluation';evaluation.mkdir(exist_ok=True)
    for name in ('REPORT.md','performance_summary.csv','browser_performance.json','native_performance.json','matched_comparison_verification.json','archived_reference_verification.json','full_size_verification.json'):
        source=ROOT/'paper/platform_evaluation'/name
        if source.exists():shutil.copy2(source,evaluation/name)
    if destination:
        destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
        for name in ('index.html','app.js','style.css','platform.js','platform.css','platform-views.html','scene.json','reference.json','study-results.json','alignment.json','THIRD_PARTY.md'):
            shutil.copy2(web/name,destination/name)
        for name in ('engine','assets','evaluation'):
            (destination/name).mkdir(exist_ok=True)
            for p in (web/name).rglob('*'):
                if p.is_file() and p.name not in ('probe.html','probe-worker.js'):
                    relative=p.relative_to(web/name);target=destination/name/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    print(json.dumps(dict(bundle_bytes=(engine/'python-source.zip').stat().st_size,dependencies=dependencies,destination=str(destination))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',type=Path)
    build(parser.parse_args().destination)
