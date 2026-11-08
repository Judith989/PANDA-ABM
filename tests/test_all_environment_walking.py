from pathlib import Path
import json,math
import pytest
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.twin.environments import synthetic_environment,satellite_environment,facility_from_environment
ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('name,expected',[('original',1106),('satellite',396),('synthetic',1106)])
def test_all_builtin_layouts_use_network_distances(name,expected):
    f=load_facility_from_lot_config(ROOT/'data/lot_config.json') if name=='original' else facility_from_environment(satellite_environment() if name=='satellite' else synthetic_environment())
    assert f.walking_network is not None
    usable=[s for s in f.spaces if not s.unavailable];assert len(usable)==expected
    for door,position in zip(f.walmart_door_ids,f.walmart_doors):
        for s in usable:
            distance=f.walking_network.distance(s.space_id,door)
            assert math.isfinite(distance)
            assert distance+1e-5>=math.dist((s.x_m,s.y_m),position)
    s=usable[len(usable)//2];route=f.walking_network.route(s.space_id,f.walmart_door_ids[0])
    assert route and len(route['points'])>2
    assert abs(route['distance_m']-f.walking_network.distance(s.space_id,f.walmart_door_ids[0]))<1e-6

FIELDS=['id','module','local_x_m','local_y_m','heading_deg','heading_reference','is_accessible','is_reserved','is_unavailable','is_blocked']

def geometry(config):
    return [{k:s.get(k) for k in FIELDS} for s in config['slots']],[(d['id'],d['local_x_m'],d['local_y_m']) for d in config['walmart_doors']]

def test_walking_addition_preserves_bay_geometry_and_restrictions():
    # Pre-walking original configuration (local research archive, not versioned).
    before=ROOT/'research/walmart_pedestrians_20261105/before_lot_config.json'
    if not before.exists():pytest.skip('Local research archive not present')
    old=json.loads(before.read_text(encoding='utf8'))
    new=json.loads((ROOT/'data/lot_config.json').read_text(encoding='utf8'))
    assert geometry(old)==geometry(new)

def test_satellite_bay_geometry_and_restrictions_unchanged():
    # The pre-walking satellite file was never committed; guard the geometry as of 2026-11-07.
    import hashlib
    new=json.loads((ROOT/'data/lot_config.satellite_estimated.json').read_text(encoding='utf8'))
    fingerprint=hashlib.sha256(json.dumps(list(geometry(new)),sort_keys=True).encode()).hexdigest()
    assert fingerprint=='68a26fcff8120c1c3360e699ecdf9ec084251ab19afe1801c0ca77ee5a1e0ef0'
