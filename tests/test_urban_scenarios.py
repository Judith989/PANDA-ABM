"""Urban mechanisms on a controlled small network, not a downtown field validation."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import math,json,struct
import pytest
from panda_abm.twin.environments import validate_environment,facility_from_environment,ROOT
from panda_abm.twin.replay import build_replay_model,record_run,LiveSimulation,validate_settings
from panda_abm.twin.platform import simulate
from panda_abm.environment.navigation import AisleNetwork
from panda_abm.core.traffic import AisleTraffic
from panda_abm.core.states import DriverState
from panda_abm.core.urban_traffic import apply_controls

@pytest.fixture
def env():
    points=[dict(id='a',local_x_m=0,local_y_m=0),dict(id='c',local_x_m=40,local_y_m=40)]
    config=dict(meta=dict(lot_name='Controlled urban test',ref_lat=41.31,ref_lon=-105.59),destinations=[dict(id='destination',local_x_m=30,local_y_m=20)],entry_points=points,exit_points=points,
        slots=[dict(id='street',module='road',local_x_m=40,local_y_m=4,parking_kind='on_street',time_limit_minutes=120),dict(id='lot',module='lot',local_x_m=36,local_y_m=40,parking_kind='off_street')],
        aisle_network=dict(nodes=dict(a=[0,0],b=[40,0],c=[40,40],d=[0,40]),edges=[['a','b'],['b','c'],['c','d'],['d','a']],directed=True,aisles=dict(road=['a','b'],lot=['b','c']),space_access=dict(street=dict(node='b',aisle='road'),lot=dict(node='c',aisle='lot')),access_nodes=dict(a='a',c='c')))
    return validate_environment(dict(id='controlled',config=config))

def test_directed_routes_and_mid_edge_anchors(env):
    nav=AisleNetwork(facility_from_environment(env));a=nav._point_nodes[(0.,0.)]
    route=nav.route((20,0),a)
    assert route[1]==(40.,0.) and (40.,40.) in route and route[-1]==(0.,0.)
    assert nav.distances((20,0))[a]==pytest.approx(140)


def test_traffic_route_change_does_not_reverse_in_the_middle_of_a_road(env):
    e=deepcopy(env);network=e['config']['aisle_network'];network['directed']=False
    nav=AisleNetwork(facility_from_environment(validate_environment(e)))
    target=nav._point_nodes[(0.,0.)]
    route=nav.route((20.,0.),target,heading=(1.,0.))
    assert route[1]==(40.,0.)
    assert (40.,40.) in route and (0.,40.) in route
    assert nav.distances((20.,0.),heading=(1.,0.))[target]==pytest.approx(140.)

def test_visit_profiles_policies_and_matched_attributes(env):
    for name,low,high in [('short',900,3600),('near_limit',5400,7200),('long',9000,14400)]:
        settings=dict(environment=env,visit_profile=name,population_size=20,seed=33)
        _,f,p,_=build_replay_model(settings)
        assert all(low<=d.attributes.expected_dwell_duration_s<=high for d in p.drivers)
        _,_,q,_=build_replay_model(settings|dict(parking_policy='unrestricted',model='rum',information='space'))
        assert [d.attributes for d in p.drivers]==[d.attributes for d in q.drivers]
        if name=='long':assert all(not f.spaces[0].permits_planned_stay(d.attributes) for d in p.drivers)
    s=validate_settings(dict(demand_duration_s=14400,arrival_interval_s=60,simulation_duration_s=21600))
    assert s['population_size']==240
    with pytest.raises(ValueError):validate_settings(dict(demand_duration_s=21600,arrival_interval_s=1))

def test_signals_stop_and_clearance(env):
    e=deepcopy(env);e['config']['aisle_network']['controls']=[dict(node='b',type='signal',cycle_s=30,east_west_green=[0,10],north_south_green=[15,25])]
    e=validate_environment(e);_,_,_,model=build_replay_model(dict(environment=e,traffic_enabled=True,population_size=1))
    car=SimpleNamespace(driver_id='probe',x_m=30.,y_m=0.,route=[(40.,0.),(40.,40.)],state=DriverState.EXITING)
    traffic=model.traffic;poses={'probe':((30.,0.),(1.,0.))}
    model.clock_s=12;traffic.budgets={'probe':5};apply_controls(traffic,[car],poses)
    assert traffic.budgets['probe']==pytest.approx(10-traffic.vehicle_length_m-traffic.minimum_gap_m) and car.traffic_reason=='red_signal'
    model.clock_s=2;traffic.budgets={'probe':5};apply_controls(traffic,[car],poses)
    assert traffic.budgets['probe']==5
    # Once past the stop line, a phase change must let the vehicle clear.
    model.clock_s=12;car.x_m=37.;poses={'probe':((37.,0.),(1.,0.))}
    traffic.budgets={'probe':5};apply_controls(traffic,[car],poses)
    assert traffic.budgets['probe']==5
    e['config']['aisle_network']['controls'][0]=dict(node='b',type='stop',dwell_s=2)
    model.facility=facility_from_environment(e);car.x_m=35;poses={'probe':((35.,0.),(1.,0.))}
    model.clock_s=0;traffic.budgets={'probe':5};apply_controls(traffic,[car],poses);assert traffic.budgets['probe']==0
    model.clock_s=2;traffic.budgets={'probe':5};apply_controls(traffic,[car],poses);assert traffic.budgets['probe']==5

def test_through_traffic_counts_recording_and_live_agreement(env):
    settings=dict(environment=env,traffic_enabled=True,through_traffic='high',through_demand_s=60,simulation_duration_s=120,population_size=2,information='space',seed=19)
    replay=record_run(settings);native=simulate(settings);live=LiveSimulation(settings);end=live.advance(120)
    assert replay['summary']==end['summary']
    assert replay['summary']['drivers']==2 and len(replay['outcomes'])==2
    assert replay['through_traffic']['scheduled']==4 and native['through_traffic']==replay['through_traffic']
    tracks=[t for t in replay['tracks'] if t['role']=='through_traffic'];assert len(tracks)==4
    assert any(len(t['samples'])>2 for t in tracks)
    assert all(t['id'].startswith('T') for t in tracks)
    assert live.frame()['through_traffic']==replay['through_traffic']
    rows={r[0]:r for frame in end['frames'] for r in frame['vehicles']}
    for track in tracks:
        assert rows[track['id']][1:5]==track['samples'][-1][1:5]

def test_osm_building_glb_and_context_manifest():
    p=ROOT/'dashboard/assets/downtown_buildings.glb';data=p.read_bytes();magic,version,length=struct.unpack('<III',data[:12])
    assert magic==0x46546c67 and version==2 and length==len(data)
    n,kind=struct.unpack('<II',data[12:20]);doc=json.loads(data[20:20+n]);assert doc['meshes'] and doc['accessors'][0]['count']>0
    draft=json.loads((ROOT/'research/downtown_review/20261105/environment.review.json').read_text(encoding='utf8'))
    assert draft['config']['meta']['review_required'] and draft['config']['buildings']
    assert draft['alignment']['up_axis']=='Z'
    assert draft['config']['aisle_network']['directed'] and len(draft['config']['aisle_network']['controls'])==5


def test_turn_restriction_routes_around_forbidden_movement(env):
    e=deepcopy(env);n=e['config']['aisle_network'];n['edges'] += [['b','a'],['c','b'],['d','c'],['a','d']]
    n['turn_restrictions']=[['a','b','c']];e=validate_environment(e)
    nav=AisleNetwork(facility_from_environment(e));node=nav._point_nodes[(40.,40.)]
    route=nav.route((0.,0.),node)
    assert route[1:]==[(0.,0.),(0.,40.),(40.,40.)]

def test_field_validation_requires_real_matched_rows(tmp_path):
    import importlib.util
    spec=importlib.util.spec_from_file_location('urban_field',ROOT/'scripts/evaluate_urban_field_data.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    observed=tmp_path/'observed.csv';pred=tmp_path/'pred.csv'
    observed.write_text('location_id,time_s,split,queue_vehicles,speed_m_s\nA,1,validation,2,4\nA,2,training,100,100\n',encoding='utf8')
    pred.write_text('location_id,time_s,queue_vehicles,speed_m_s\nA,1,3,2\nA,2,0,0\n',encoding='utf8')
    report=module.evaluate(observed,pred)
    assert report['validation_rows']==1 and report['metrics']['queue_vehicles']['mae']==1
    assert report['metrics']['speed_m_s']['mean_error']==-2


def test_residual_background_departures_respect_initial_occupants(env):
    _,_,_,model=build_replay_model(dict(environment=env,background_departures='residual',occupancy=1,population_size=1,visit_profile='long'))
    departures=dict((sid,t) for t,sid in model.background_departures.heap)
    assert 1<=departures['street']<=7200 and 1<=departures['lot']<=14400
    model.clock_s=max(departures.values())+1;model.background_departures.step()
    assert all(not s.occupied for s in model.space_states.values())

