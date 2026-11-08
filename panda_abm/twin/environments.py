"""Validated, self-contained environments for the public simulation adapters."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path

from panda_abm.environment import load_facility_from_lot_config
from panda_abm.environment.facility import Facility
from panda_abm.environment.parking_space import parking_space_from_lot_config_slot
from panda_abm.environment.navigation import AisleNetwork

ROOT = Path(__file__).resolve().parents[2]


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def number(value, label, low=-100000, high=100000):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be a finite number from {low} to {high}')
    return float(value)


def identifier(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError(f'{label} must be a nonempty string of at most 100 characters')
    return value


def validate_environment(payload):
    """Validate on the execution side as well as in the upload interface."""
    if not isinstance(payload, dict): raise ValueError('Environment must be a JSON object')
    if len(json.dumps(payload, allow_nan=False)) > 8_000_000: raise ValueError('Environment JSON exceeds 8 MB')
    raw = deepcopy(payload.get('config', payload))
    if not isinstance(raw, dict): raise ValueError('Lot config must be an object')
    meta = raw.get('meta', {})
    for key, low, high in [('ref_lat', -85, 85), ('ref_lon', -180, 180)]:
        number(meta.get(key), key, low, high)
    name = identifier(meta.get('lot_name'), 'Lot name')
    slots = raw.get('slots')
    if not isinstance(slots, list) or not 2 <= len(slots) <= 2000:
        raise ValueError('Provide 2–2,000 parking spaces')
    ids = set()
    positions = set()
    for s in slots:
        sid = identifier(s.get('id'), 'Space ID')
        if sid in ids: raise ValueError(f'Duplicate space ID: {sid}')
        ids.add(sid)
        identifier(s.get('module') or s.get('module_id'), 'Space module')
        x, y = (number(s.get(k), f'{sid} {k}') for k in ('local_x_m', 'local_y_m'))
        if (x, y) in positions: raise ValueError(f'Duplicate space centre: {sid}')
        positions.add((x, y))
        for key in ('is_accessible', 'is_reserved', 'is_blocked', 'is_unavailable'):
            if key in s and type(s[key]) is not bool: raise ValueError(f'{sid} {key} must be true or false')
        number(s.get('price_per_hour', 0), 'Price', 0, 10000)
        if s.get('time_limit_minutes') is not None: number(s['time_limit_minutes'], 'Time limit (minutes)', 1, 1440)
    # Schema v2 uses destination IDs; preserve the legacy adapter for old runs.
    if 'destinations' in raw:
        if 'walmart_doors' in raw and raw['walmart_doors'] != raw['destinations']:
            raise ValueError('destinations and legacy walmart_doors must agree')
        raw['walmart_doors'] = deepcopy(raw['destinations'])
    for key in ('walmart_doors', 'entry_points', 'exit_points'):
        points = raw.get(key, [])
        if not isinstance(points, list) or not 1 <= len(points) <= 64:
            raise ValueError(f'{key} requires 1–64 locations')
        point_ids = [identifier(p.get('id'), key+' ID') for p in points]
        if len(set(point_ids)) != len(point_ids): raise ValueError(f'Duplicate {key} IDs')
        raw[key] = sorted(points, key=lambda p: p['id'])
        for p in raw[key]:
            for k in ('local_x_m', 'local_y_m'): number(p.get(k), f'{p["id"]} {k}')
            p['lat'] = meta['ref_lat'] + p['local_y_m']/111000
            p['lon'] = meta['ref_lon'] + p['local_x_m']/(111000*math.cos(math.radians(meta['ref_lat'])))
    # Different entry and exit inventories are supported; shared IDs identify the same location.
    if 'destinations' in raw: raw['destinations'] = deepcopy(raw['walmart_doors'])
    # The current population links entry and intended exit by the same ID.
    exits_by_id={p['id']:p for p in raw['exit_points']}
    for point in raw['entry_points']:
        other=exits_by_id.get(point['id'])
        if other and math.dist((point['local_x_m'],point['local_y_m']),(other['local_x_m'],other['local_y_m']))>1e-6:
            raise ValueError('Shared entry/exit IDs must have identical coordinates')
    raw['parking_lot_exits'] = deepcopy(raw['exit_points'])
    for s in slots:
        for key, points in [('door',raw['walmart_doors']), ('exit',raw['exit_points'])]:
            for p in points:
                s[f'distance_to_{p["id"]}_m'] = math.dist((s['local_x_m'],s['local_y_m']), (p['local_x_m'],p['local_y_m']))
        s['lat'] = meta['ref_lat'] + s['local_y_m']/111000
        s['lon'] = meta['ref_lon'] + s['local_x_m']/(111000*math.cos(math.radians(meta['ref_lat'])))
        # Validate per-space dimensions used for display only.
        for k, default in [('length_m',4.9), ('width_m',2.06)]: number(s.get(k,default), k, .5, 25)
        number(s.get('heading_deg',0), 'Space heading', -360, 360)
        if s.get('heading_reference','counterclockwise_from_east') not in ('counterclockwise_from_east','clockwise_from_north'): raise ValueError('Unknown space heading reference')
    usable = sum(not (s.get('is_unavailable') or s.get('is_blocked')) for s in slots)
    if not usable: raise ValueError('At least one usable space is required')
    network = raw.get('aisle_network')
    if not isinstance(network, dict): raise ValueError('Provide aisle_network with nodes, edges, aisles, space_access and access_nodes')
    network['bay_geometry']={s['id']:{k:s[k] for k in ('heading_deg','heading_reference','length_m','width_m') if k in s} for s in slots}
    network['building_footprints_m']={b['id']:b['footprint_m'] for b in raw.get('buildings',[])}
    if 'directed' in network and type(network['directed']) is not bool: raise ValueError('directed must be Boolean')
    nodes = network.get('nodes', {})
    if not isinstance(nodes, dict) or not 2 <= len(nodes) <= 6000: raise ValueError('Provide 2–6,000 aisle nodes')
    for nid, xy in nodes.items():
        identifier(nid,'Node ID')
        if not isinstance(xy,list) or len(xy)!=2: raise ValueError('Each aisle node needs [east_m, north_m]')
        for v in xy: number(v,'Node coordinate')
    edges = network.get('edges', [])
    if not isinstance(edges,list) or not 1 <= len(edges) <= 12000: raise ValueError('Provide 1–12,000 edges')
    for pair in edges:
        if not isinstance(pair,list) or len(pair)!=2 or any(n not in nodes for n in pair) or pair[0]==pair[1]: raise ValueError('Each edge must connect two distinct known nodes')
        if math.dist(nodes[pair[0]], nodes[pair[1]]) < 1e-6: raise ValueError('Aisle edges must have nonzero length')
    aisles = network.get('aisles', {})
    if not isinstance(aisles,dict) or not aisles: raise ValueError('Define aisle IDs and their endpoint node pairs')
    for aid,pair in aisles.items():
        identifier(aid,'Aisle ID')
        if not isinstance(pair,list) or len(pair)!=2 or any(n not in nodes for n in pair) or pair[0]==pair[1]: raise ValueError('Aisle endpoints must be distinct known nodes')
    labels=network.get('segment_labels',{})
    if not isinstance(labels,dict) or any(k not in aisles for k in labels):raise ValueError('Segment labels must refer to configured aisles')
    for value in labels.values():
        if not isinstance(value,dict) or any(not isinstance(v,str) or len(v)>250 for v in value.values()):raise ValueError('Segment labels must contain short text values')
    for key, required in [('space_access',ids),('access_nodes',{p['id'] for p in raw['entry_points']+raw['exit_points']})]:
        mapping=network.get(key,{})
        if not isinstance(mapping,dict) or set(mapping)!=required: raise ValueError(f'{key} must cover every required ID exactly once')
        for item,value in mapping.items():
            if key=='space_access':
                if not isinstance(value,dict) or value.get('node') not in nodes or value.get('aisle') not in aisles: raise ValueError(f'Invalid road node or aisle for {item}')
            elif value not in nodes: raise ValueError('Access node is missing')
    turns=network.get('turn_restrictions',[])
    if not isinstance(turns,list) or len(turns)>500: raise ValueError('Too many turn restrictions')
    for turn in turns:
        if not isinstance(turn,list) or len(turn)!=3 or any(n not in nodes for n in turn):raise ValueError('Turn restrictions require three known nodes')
        if [turn[0],turn[1]] not in edges or [turn[1],turn[2]] not in edges:raise ValueError('Restricted turn must follow existing directed edges')
    controls=network.get('controls',[])
    if not isinstance(controls,list) or len(controls)>100: raise ValueError('Too many intersection controls')
    if len({c.get('node') for c in controls})!=len(controls): raise ValueError('Duplicate intersection control')
    for control in controls:
        if control.get('node') not in nodes: raise ValueError('Unknown controlled node')
        if control.get('type')=='signal':
            cycle=number(control.get('cycle_s'), 'Signal cycle',10,600)
            number(control.get('offset_s',0),'Signal offset',0,600)
            for axis in ('east_west_green','north_south_green'):
                interval=control.get(axis)
                if not isinstance(interval,list) or len(interval)!=2 or not 0<=interval[0]<interval[1]<=cycle: raise ValueError('Invalid signal green interval')
            ew,ns=control['east_west_green'],control['north_south_green']
            if max(ew[0],ns[0])<min(ew[1],ns[1]): raise ValueError('Conflicting signal phases')
        elif control.get('type')=='stop':number(control.get('dwell_s',2),'Stop dwell',1,20)
        else: raise ValueError('Unknown control type')
    alignment=deepcopy(payload.get('alignment') or dict(east_m=0,north_m=0,height_m=0,rotation_radians=0,scale=1,up_axis='Y',forward_axis='X'))
    alignment.setdefault('up_axis','Y');alignment.setdefault('forward_axis','X')
    for key in ('east_m','north_m','height_m','rotation_radians'): number(alignment.get(key),key)
    number(alignment.get('scale'),'Model scale',.0001,10000)
    if alignment.get('up_axis','Y') not in ('Y','Z') or alignment.get('forward_axis','X') not in ('X','Z') or alignment.get('up_axis')==alignment.get('forward_axis'):
        raise ValueError('Choose distinct model up and forward axes')
    model_files=payload.get('model_files',[])
    if not isinstance(model_files,list) or len(model_files)>8: raise ValueError('At most eight GLB models are supported')
    for f in model_files:
        if not isinstance(f,dict) or set(f)-{'name','sha256','label'}: raise ValueError('Model entries need name, sha256 and an optional label')
        identifier(f.get('name'),'Model filename')
        # Optional user-chosen display name; the filename still identifies the file.
        if 'label' in f and (not isinstance(f['label'],str) or not f['label'].strip() or len(f['label'])>80): raise ValueError('Model names must be 1–80 characters')
        if not f['name'].lower().endswith('.glb') or '/' in f['name'] or '\\' in f['name']: raise ValueError('Use GLB filenames without folder paths')
        digest=f.get('sha256','')
        if len(digest)!=64 or any(ch not in '0123456789abcdef' for ch in digest): raise ValueError('Model SHA-256 is required')
    if len({f['name'] for f in model_files})!=len(model_files): raise ValueError('Duplicate model filenames')
    result=dict(id=identifier(payload.get('id','uploaded'),'Environment ID'), name=name,config=raw,alignment=alignment,model_files=model_files)
    from panda_abm.environment.pedestrian_navigation import validate_pedestrian_network
    validate_pedestrian_network(raw)
    facility=facility_from_environment(result)
    navigation=AisleNetwork(facility)  # Connectivity and reachability checked before commit.
    result['config_sha256']=checksum(raw)
    result['environment_sha256']=checksum({k:result[k] for k in ('config','alignment','model_files')})
    result['validation']=dict(spaces=len(slots),usable_spaces=usable,nodes=len(navigation.positions),edges=len(navigation.graph.edges()),warnings=[
        'Network connectivity was checked; road placement, turning clearance and building conflicts require visual inspection.',
        'Destination and paired access counts are configurable; directions, walking routes and restrictions require review.'])
    return result


def facility_from_environment(environment):
    raw=environment['config']
    points=lambda key:tuple((p['local_x_m'],p['local_y_m']) for p in raw[key])
    return Facility(facility_id=environment['id'], name=raw['meta']['lot_name'],
        spaces=tuple(parking_space_from_lot_config_slot(s) for s in raw['slots']),
        entry_points=points('entry_points'),exit_points=points('exit_points'),
        walmart_doors=points('walmart_doors'),entry_point_ids=tuple(p['id'] for p in raw['entry_points']),
        exit_point_ids=tuple(p['id'] for p in raw['exit_points']),walmart_door_ids=tuple(p['id'] for p in raw['walmart_doors']),
        synthetic=raw['meta'].get('synthetic',False),aisle_network=raw['aisle_network'],pedestrian_network=raw.get('pedestrian_network'))


def traffic_segment_labels(facility,navigation=None):
    labels=deepcopy((facility.aisle_network or {}).get('segment_labels',{}))
    if 'walmart' not in facility.name.lower():return labels
    nav=navigation or AisleNetwork(facility)
    spaces=facility.space_by_id
    for index,aid in enumerate(nav.aisle_nodes,1):
        if aid in labels:continue
        modules=sorted({spaces[sid].module_id.replace('Parking_Module_','Module ') for sid in nav.aisle_spaces.get(aid,())})
        name=f'Parking aisle {index:02}'
        labels[aid]=dict(road_name=name,modules=', '.join(modules),label=name+(' — serves '+', '.join(modules) if modules else ''))
    return labels


def export_network(facility):
    n=AisleNetwork(facility)
    def approach_node(stall):
        choices=[v for v in n.graph.neighbors(stall) if v!=stall]
        return min(choices,key=lambda v:(v in set(n.space_nodes.values()),math.dist(n.positions[v],n.positions[stall]),v)) if choices else stall
    return dict(segment_labels=traffic_segment_labels(facility,n),nodes={str(k):list(v) for k,v in n.positions.items()},edges=[[str(a),str(b)] for a,b in n.graph.edges()],
        aisles={k:[str(a),str(b)] for k,(a,b) in n.aisle_nodes.items()},
        space_access={sid:dict(node=str(approach_node(node)),aisle=n.space_aisle[sid]) for sid,node in n.space_nodes.items()},
        access_nodes={pid:str(n._point_nodes[tuple(round(v,8) for v in p)]) for pid,p in zip(facility.exit_point_ids,facility.exit_points)})


def synthetic_environment():
    saved=ROOT/'data/lot_config.synthetic.json'
    if saved.exists():return validate_environment(dict(id='synthetic',config=json.loads(saved.read_text(encoding='utf8'))))
    from panda_abm.simulation.tcss_conditions import transfer_facility
    source=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    f=transfer_facility(source)
    original=json.loads((ROOT/'data/lot_config.json').read_text())
    old={s['id']:s for s in original['slots']}
    slots=[]
    for s in f.spaces:
        row=deepcopy(old[s.space_id]);row.update(module=s.module_id,local_x_m=s.x_m,local_y_m=s.y_m)
        row.pop('legacy_geometry',None);slots.append(row)
    point=lambda ids,values:[dict(id=i,local_x_m=p[0],local_y_m=p[1]) for i,p in zip(ids,values)]
    raw=dict(meta=dict(lot_name='Downtown Laramie synthetic experiment',ref_lat=41.3105,ref_lon=-105.5950,synthetic=True,show_basemap=True,location_note='Fictional experimental layout anchored near downtown Laramie; not a reconstruction of an existing parking facility.'),slots=slots,
        walmart_doors=point(f.walmart_door_ids,f.walmart_doors),entry_points=point(f.entry_point_ids,f.entry_points),
        exit_points=point(f.exit_point_ids,f.exit_points),aisle_network=export_network(f))
    return validate_environment(dict(id='synthetic',config=raw))

def example_environment():
    """Small editable template; every space has an explicit road/aisle assignment."""
    from panda_abm.simulation.tcss_conditions import transfer_facility
    source=transfer_facility(load_facility_from_lot_config(ROOT/'data/lot_config.json'))
    chosen=source.spaces[:6]+source.spaces[79:85]
    f=replace(source,spaces=chosen)
    point=lambda ids,values:[dict(id=i,local_x_m=p[0],local_y_m=p[1]) for i,p in zip(ids,values)]
    raw=dict(meta=dict(lot_name='Example parking environment',ref_lat=41.3105,ref_lon=-105.5950,synthetic=True,show_basemap=True),
        slots=[dict(id=s.space_id,module=s.module_id,local_x_m=s.x_m,local_y_m=s.y_m,is_accessible=s.accessible,is_reserved=s.reserved_type is not None,is_unavailable=False,is_blocked=False,type=s.space_type.value) for s in chosen],
        walmart_doors=point(f.walmart_door_ids,f.walmart_doors),entry_points=point(f.entry_point_ids,f.entry_points),
        exit_points=point(f.exit_point_ids,f.exit_points),aisle_network=export_network(f))
    return validate_environment(dict(id='example',config=raw))


def satellite_environment():
    """Opt-in satellite estimate; the original 1,315-record configuration is untouched."""
    raw=json.loads((ROOT/'data/lot_config.satellite_estimated.json').read_text(encoding='utf8'))
    # Reuse the navigation inference including west/east side corridors, then
    # export an explicit graph for the shared environment execution path.
    points=lambda key:tuple((p['local_x_m'],p['local_y_m']) for p in raw[key])
    facility=Facility('walmart_satellite',raw['meta']['lot_name'],
        tuple(parking_space_from_lot_config_slot(s) for s in raw['slots']),
        points('entry_points'),points('exit_points'),walmart_doors=points('walmart_doors'),
        entry_point_ids=('exit_a','exit_b'),exit_point_ids=('exit_a','exit_b'),walmart_door_ids=('door_1','door_2'),pedestrian_network=raw.get('pedestrian_network'),aisle_network=raw.get('aisle_network'))
    raw['aisle_network']=export_network(facility)
    return validate_environment(dict(id='walmart_satellite',config=raw))


def corrected_environment():
    """Default planning layout: Walmart double rows corrected from satellite imagery.

    The original 1,315-record configuration behind the published results is untouched.
    """
    raw=json.loads((ROOT/'data/lot_config.corrected_imagery.json').read_text(encoding='utf8'))
    return validate_environment(dict(id='walmart_corrected',config=raw))


def asset_path(name):
    """Generated dashboard asset, else the committed release copy (fresh clones)."""
    local=ROOT/'dashboard/assets'/name
    return local if local.exists() else ROOT/'web/release/assets'/name


def downtown_environment():
    """Regular downtown platform environment; the earlier review snapshot is retained."""
    raw=json.loads((ROOT/'data/lot_config.downtown_laramie.json').read_text(encoding='utf8'))
    return validate_environment(dict(id='downtown_laramie',config=raw,
        alignment=dict(east_m=0,north_m=0,height_m=0,rotation_radians=0,scale=1,up_axis='Z',forward_axis='X',context_note='OSM building footprints with illustrative heights; visualization only.'),
        model_files=[dict(name='downtown_buildings.glb',sha256=hashlib.sha256(asset_path('downtown_buildings.glb').read_bytes()).hexdigest())]))
