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

@pytest.mark.parametrize('filename',['lot_config.json','lot_config.satellite_estimated.json'])
def test_walking_addition_preserves_bay_geometry_and_restrictions(filename):
    old=json.loads((ROOT/'research/walmart_pedestrians_20261105'/('before_'+filename)).read_text(encoding='utf8'))
    new=json.loads((ROOT/'data'/filename).read_text(encoding='utf8'))
    fields=['id','module','local_x_m','local_y_m','heading_deg','heading_reference','is_accessible','is_reserved','is_unavailable','is_blocked']
    assert [{k:s.get(k) for k in fields} for s in old['slots']]==[{k:s.get(k) for k in fields} for s in new['slots']]
    assert [(d['id'],d['local_x_m'],d['local_y_m']) for d in old['walmart_doors']]==[(d['id'],d['local_x_m'],d['local_y_m']) for d in new['walmart_doors']]
