"""Routes, utility, restrictions, timing and dynamic crossing safety use one network."""
import math
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
import pytest
from panda_abm.twin.environments import validate_environment,facility_from_environment
from panda_abm.twin.replay import build_replay_model
from panda_abm.environment.choice_set import ChoiceSetBuilder
from panda_abm.environment.perception import PerceivedSpace
from panda_abm.core.states import DriverState
from panda_abm.core.pedestrian_movement import safe_to_cross,advance_walk,yield_to_pedestrians
from panda_abm.environment.pedestrian_geometry import ObstacleIndex,bay_polygon

@pytest.fixture
def env():
    points=[dict(id='entry',local_x_m=-10,local_y_m=-10),dict(id='exit',local_x_m=20,local_y_m=-10)]
    nodes=dict(p0=[-8,0],p1=[-8,5],p2=[10,5],door=[10,0],p4=[-8,10])
    raw=dict(meta=dict(lot_name='Walking detour test',ref_lat=41.31,ref_lon=-105.59),destinations=[dict(id='door',local_x_m=10,local_y_m=0)],entry_points=points,exit_points=points,
        slots=[dict(id='A',module='row',local_x_m=-10,local_y_m=0,length_m=2,width_m=2),dict(id='B',module='row',local_x_m=-10,local_y_m=10,length_m=2,width_m=2)],
        buildings=[dict(id='building',footprint_m=[[-2,-2],[2,-2],[2,2],[-2,2]])],
        aisle_network=dict(nodes=dict(n0=[-10,-10],n1=[20,-10]),edges=[['n0','n1']],aisles=dict(row=['n0','n1']),space_access=dict(A=dict(node='n0',aisle='row'),B=dict(node='n0',aisle='row')),access_nodes=dict(entry='n0',exit='n1')),
        pedestrian_network=dict(nodes=nodes,edges=[dict(from_=a,to=b,kind='sidewalk',source='controlled') for a,b in [('p0','p1'),('p1','p2'),('p2','door'),('p1','p4')]],space_access=dict(A=dict(node='p0',points=[[-10,0],[-8,0]]),B=dict(node='p4',points=[[-10,10],[-8,10]])),destination_access=dict(door='door'),road_polygons=[]))
    for edge in raw['pedestrian_network']['edges']:edge['from']=edge.pop('from_')
    return validate_environment(dict(id='detour',config=raw))

def test_network_distance_constraints_reference_and_model_features(env):
    _,f,p,m=build_replay_model(dict(environment=env,population_size=1,model='deterministic',information='space',occupancy=0))
    attrs=replace(p.drivers[0].attributes,max_walking_distance_m=None)
    assert f.walking_distance(f.spaces[0],attrs)==pytest.approx(30)
    assert f.walking_distance(f.spaces[0],attrs)>math.dist((-10,0),(10,0))
    agent=m.agents[0];agent.attributes=attrs
    for _ in range(3):m.step()
    ev=agent.last_decision.candidate_evaluations
    assert next(e.features['walking_distance_m'] for e in ev if e.space_id=='A')==pytest.approx(30)
    agent.attributes=replace(attrs,max_walking_distance_m=25)
    assert ChoiceSetBuilder().build(agent,[PerceivedSpace(f.spaces[0],0,False,True)])==[]
    limited=replace(f.spaces[0],time_limit_minutes=1)
    attrs=replace(attrs,expected_dwell_duration_s=30)
    assert limited.permits_planned_stay(attrs) and not limited.permits_planned_stay(attrs,walking_distance_m=30)
    from panda_abm.behavior.references import lot_distance_references,ReferencePoints
    r=lot_distance_references(f,attrs,ReferencePoints());assert r.r_walk_m>=30

def test_disconnected_destination_has_no_fallback(env):
    e=deepcopy(env);e['config']['pedestrian_network']['space_access']['A']=None
    f=facility_from_environment(validate_environment(e));attrs=SimpleNamespace(walmart_door_id='door')
    assert math.isinf(f.walking_distance(f.spaces[0],attrs)) and f.walking_route(f.spaces[0],attrs) is None

@pytest.mark.parametrize('bad',['building','other_bay','road'])
def test_invalid_pedestrian_connections_rejected(env,bad):
    e=deepcopy(env);raw=e['config'];net=raw['pedestrian_network']
    if bad=='building':net['edges'].append(dict(**{'from':'p0','to':'door'},kind='sidewalk'))
    if bad=='other_bay':net['space_access']['B']['points']=[[-10,10],[-10,0],[-8,10]]
    if bad=='road':net['road_polygons']=[[[0,4],[1,4],[1,6],[0,6]]]
    with pytest.raises(ValueError):validate_environment(e)

def test_walking_lifecycle_follows_route_and_returns_without_vehicle_teleport(env):
    _,f,p,m=build_replay_model(dict(environment=env,population_size=1,model='deterministic',information='space',occupancy=0))
    a=m.agents[0];a.attributes=replace(a.attributes,expected_dwell_duration_s=3,max_walking_distance_m=None)
    for _ in range(200):
        m.step()
        if a.state==DriverState.LEFT:break
    assert a.state==DriverState.LEFT
    assert a.walking_distance_m>=30 and a.pedestrian_segments
    obstacles=ObstacleIndex([('building',f.aisle_network and [[-2,-2],[2,-2],[2,2],[-2,2]])])
    for segment in a.pedestrian_segments:assert not obstacles.hits(segment['from_m'],segment['to_m'])
    assert {'to_door','to_vehicle'}=={x['phase'] for x in a.pedestrian_segments}
    assert a.pedestrian_segments[-1]['to_m']==list(a.walking_route_data['points'][0])

def test_waiting_and_vehicle_yield_at_reserved_crossing():
    car=SimpleNamespace(driver_id='car',state=DriverState.EXITING,x_m=-10.,y_m=0.,route=[(30.,0.)])
    model=SimpleNamespace(agents=[car],search_speed_m_per_s=5.,walk_speed_m_per_s=1.4,clock_s=1.,pedestrian_reservations={},traffic=SimpleNamespace(vehicle_length_m=4.5))
    walker=SimpleNamespace(driver_id='walker',model=model,walk_position=(0.,-5.),walk_points=[(0.,-5.),(0.,5.)],walk_edges=[dict(kind='crossing',crossing_id='cross')],walk_edge_index=0,walk_phase='to_door',pedestrian_segments=[],chosen_space_id='A',attributes=SimpleNamespace(walmart_door_id='door'))
    assert not safe_to_cross(walker,walker.walk_points)
    assert not advance_walk(walker,1,1) and walker.walk_position==(0.,-5.) and walker.pedestrian_wait_s==1
    car.x_m=30;car.route=[(100.,0.)];model.clock_s=2
    assert safe_to_cross(walker,walker.walk_points)
    advance_walk(walker,1,2);assert 'walker' in model.pedestrian_reservations
    car.x_m=-5.;car.route=[(30.,0.)];traffic=SimpleNamespace(model=model,budgets={'car':5.})
    yield_to_pedestrians(traffic,[car],{'car':((-5.,0.),(1.,0.))})
    assert 0<traffic.budgets['car']<=5.-4.55/2-.35
    assert car.traffic_reason=='pedestrian_crossing'


def test_stopped_vehicle_outside_yield_envelope_does_not_deadlock_crossing():
    car=SimpleNamespace(driver_id='car',state=DriverState.EXITING,x_m=-3.3,y_m=0.,route=[(30.,0.)])
    traffic=SimpleNamespace(vehicle_length_m=5.45,budgets={'car':0.})
    model=SimpleNamespace(agents=[car],search_speed_m_per_s=5.,walk_speed_m_per_s=1.4,traffic=traffic)
    walker=SimpleNamespace(model=model)
    path=[(0.,-5.),(0.,5.)]
    assert safe_to_cross(walker,path)
    car.x_m=-2.5
    assert not safe_to_cross(walker,path)
    car.x_m=-3.3;traffic.budgets['car']=5.
    assert not safe_to_cross(walker,path)
