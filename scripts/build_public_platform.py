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
import struct

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def write_json(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,separators=(',',':'),allow_nan=False),encoding='utf-8')


def synthetic_pavement(config):
    """A simple local-metre context mesh, not a surveyed facility model."""
    xs=[s['local_x_m'] for s in config['slots']];ys=[s['local_y_m'] for s in config['slots']]
    x0,x1=min(xs)-12,max(xs)+12;y0,y1=min(ys)-12,max(ys)+12
    vertices=[x0,.03,-y0,x1,.03,-y0,x1,.03,-y1,x0,.03,-y1]
    binary=struct.pack('<12f6H',*vertices,0,1,2,0,2,3)
    gltf=dict(asset=dict(version='2.0',generator='PANDA synthetic context'),scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0),indices=1,material=0)])],
        materials=[dict(doubleSided=True,pbrMetallicRoughness=dict(baseColorFactor=[.22,.27,.25,1],metallicFactor=0,roughnessFactor=1))],
        buffers=[dict(byteLength=len(binary))],bufferViews=[dict(buffer=0,byteOffset=0,byteLength=48,target=34962),dict(buffer=0,byteOffset=48,byteLength=12,target=34963)],
        accessors=[dict(bufferView=0,componentType=5126,count=4,type='VEC3',min=[x0,.03,-y1],max=[x1,.03,-y0]),dict(bufferView=1,componentType=5123,count=6,type='SCALAR')])
    data=json.dumps(gltf,separators=(',',':')).encode();data+=b' '*((-len(data))%4)
    return struct.pack('<III',0x46546c67,2,12+8+len(data)+8+len(binary))+struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(binary),0x004e4942)+binary


def build(destination=None):
    from build_pedestrian_asset import build as build_pedestrian
    build_pedestrian(ROOT/'dashboard/assets/pedestrian.glb')
    from build_vehicle_assets import build as build_vehicles
    build_vehicles(ROOT/'dashboard/assets/vehicles')
    from panda_abm.twin.replay import DEFAULTS
    from panda_abm.twin.environments import synthetic_environment, satellite_environment, example_environment, export_network, validate_environment
    from panda_abm.environment import load_facility_from_lot_config
    web=ROOT/'dashboard';engine=web/'engine';engine.mkdir(exist_ok=True)
    raw=json.loads((ROOT/'data/lot_config.json').read_text())
    raw['aisle_network']=export_network(load_facility_from_lot_config(ROOT/'data/lot_config.json'))
    walmart=validate_environment(dict(id='walmart-export',config=raw,alignment=json.loads((web/'alignment.json').read_text()),model_files=[dict(name=name,sha256=hashlib.sha256((web/'assets'/name).read_bytes()).hexdigest()) for name in ('parking_asphalt.glb','walmart_building.glb')]))
    synthetic=synthetic_environment()
    mesh=synthetic_pavement(synthetic['config']);(web/'assets/synthetic_pavement.glb').write_bytes(mesh)
    synthetic['model_files']=[dict(name='synthetic_pavement.glb',sha256=hashlib.sha256(mesh).hexdigest())]
    synthetic=validate_environment(synthetic)
    with zipfile.ZipFile(web/'assets/downtown-synthetic.zip','w',zipfile.ZIP_DEFLATED) as sample:
        sample.writestr('environment.json',json.dumps(synthetic,indent=2,allow_nan=False))
        sample.writestr('synthetic_pavement.glb',mesh)
        sample.writestr('README.txt','Fictional parking environment near downtown Laramie. Not an existing facility.\nExtract this ZIP. In PANDA choose Import a 3D environment, select environment.json and synthetic_pavement.glb, then Validate and preview. Confirm the alignment before simulating.\nThe 1,106-space local geometry, restrictions and driving network match the synthetic transfer experiment; only its geographic anchor and descriptive metadata differ.\n')
    satellite=satellite_environment()
    satellite['alignment']=dict(walmart['alignment'])
    for key in ('fit_rmse_m','max_residual_m','matched_ids'):satellite['alignment'].pop(key,None)
    satellite['alignment']['context_note']='Original Walmart building and pavement context reused. Its fit to the satellite-estimated bays has not been calibrated.'
    satellite['model_files']=walmart['model_files']
    satellite=validate_environment(satellite)
    template=example_environment()
    from panda_abm.twin.environments import downtown_environment
    downtown=downtown_environment()
    write_json(web/'environments.json',dict(synthetic=synthetic,satellite=satellite,walmart=walmart,template=template,downtown=downtown))
    files={p.relative_to(ROOT).as_posix():p for p in (ROOT/'panda_abm').rglob('*.py')}
    files['data/lot_config.json']=ROOT/'data/lot_config.json'
    if (ROOT/'data/lot_config.synthetic.json').exists():files['data/lot_config.synthetic.json']=ROOT/'data/lot_config.synthetic.json'
    files['data/lot_config.satellite_estimated.json']=ROOT/'data/lot_config.satellite_estimated.json'
    files['data/lot_config.downtown_laramie.review.json']=ROOT/'data/lot_config.downtown_laramie.review.json'
    files['data/lot_config.downtown_laramie.json']=ROOT/'data/lot_config.downtown_laramie.json'
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
        environment_assets_sha256={name:hashlib.sha256((web/name).read_bytes()).hexdigest() for name in ('environments.json','assets/synthetic_pavement.glb','assets/downtown_buildings.glb','assets/downtown-synthetic.zip','assets/pedestrian.glb',*[f'assets/vehicles/{k}.glb' for k in ('compact','sedan','suv','van','truck')])},
        runtime_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((engine/'runtime').glob('*')) if p.is_file()},
        interface_sha256={name:hashlib.sha256((web/name).read_bytes()).hexdigest() for name in ('index.html','app.js','environments.js','motion.js','pedestrians.js','follow-camera.js','platform.js','platform.css','platform-views.html','SUPPLY_TRAFFIC.md','ENVIRONMENTS.md','engine/worker.js','engine/client.js')})
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
        for name in ('index.html','app.js','environments.js','motion.js','pedestrians.js','follow-camera.js','environments.json','style.css','platform.js','platform.css','platform-views.html','scene.json','reference.json','study-results.json','alignment.json','THIRD_PARTY.md','SUPPLY_TRAFFIC.md','ENVIRONMENTS.md'):
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
