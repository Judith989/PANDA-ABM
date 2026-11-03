from dataclasses import replace,asdict
import math
import pytest
from panda_abm.behavior import DriverAttributes,DriverSpec,PopulationSpec,BehavioralParameters,ReferencePoints
from panda_abm.behavior.continuous import make_population
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import Facility,ParkingSpace,generate_synthetic_facility


def small(mode='unaided',drivers=1,**kwargs):
    facility=Facility('information','information',(
        ParkingSpace('near_blocked','A',0,0,unavailable=True),
        ParkingSpace('far_1','A',0,100),ParkingSpace('far_2','A',0,180)),
        ((-20,-8),),((-20,-8),),synthetic=True)
    pop=PopulationSpec('p',19,tuple(DriverSpec(DriverAttributes(str(i),0,100,expected_dwell_duration_s=900),
        BehavioralParameters(acceptance_utility_threshold=0),ReferencePoints()) for i in range(drivers)))
    return ParkingModel(facility,pop,seed=19,initial_occupancy_rate=0,perception_radius_m=8,
        information_mode=mode,**kwargs)


def test_space_information_exposes_current_remote_spaces_only():
    model=small('space');a=next(iter(model.agents))
    model.resource_manager.claim_space('background','far_2')
    observations=model.perceive(a)
    free={o.space.space_id for o in observations if o.perceived_available}
    assert free=={'far_1'}
    assert all(o.information_source=='space_report' and o.observed_at_s==0 for o in observations)
    assert all(o.forecast_available_probability is None for o in observations)
    assert model.build_choice_set(a,observations)[0].space_id=='far_1'


@pytest.mark.parametrize('mode',['unaided','aisle'])
def test_unaided_and_aisle_stall_choices_remain_local(mode):
    model=small(mode);a=next(iter(model.agents))
    assert all(o.distance_from_driver_m<=8 for o in model.perceive(a))
    model.run_until_complete()
    assert a.parking_time_s is not None
    targets=[e for e in model.event_logger.records if e.event_type=='TargetSelected']
    assert all(e.details['target_distance_at_selection_m']<=8+1e-9 for e in targets)
    assert a.remote_targets_selected==0
    assert (a.information_reports_received>0)==(mode=='aisle')


def test_aisle_counts_do_not_reveal_which_remote_slot_is_free():
    outputs=[]
    for occupied in ('far_1','far_2'):
        model=small('aisle');a=next(iter(model.agents))
        model.resource_manager.claim_space('background',occupied)
        report=model.aisle_information.snapshot(a)
        model.aisle_information.plan_search(a,report)
        outputs.append((asdict(report),a.information_aisle_id,list(a.route)))
    assert outputs[0]==outputs[1]
    assert set(outputs[0][0])=={'observed_at_s','free_counts','compatible_capacity'}


def test_counts_respect_static_permissions_without_revealing_locations():
    model=small('aisle');a=next(iter(model.agents))
    # Physical constraints affect the compatible count, independent of labels.
    a.attributes=replace(a.attributes,max_walking_distance_m=5)
    report=model.aisle_information.snapshot(a)
    assert sum(report.compatible_capacity.values())==1
    assert sum(report.free_counts.values())==1


def test_space_information_is_not_a_reservation_or_future_oracle():
    model=small('space',drivers=2)
    # Both drivers can initially select the same currently free space. Occupancy
    # can change after selection; refresh is at scans, not an instant reroute.
    model.resource_manager.claim_space('background','far_2')
    agents=list(model.agents)
    model.step()
    assert all(a.chosen_space_id=='far_1' and a.state==DriverState.TARGETING for a in agents)
    model.run_until_complete()
    assert sum(a.parking_time_s is not None for a in agents)==1
    assert sum(a.lost_space_events for a in agents)>=1
    assert all(a.search_time_s==a.search_ended_s-a.search_started_s for a in agents)
    assert all(a.search_time_s<=600 for a in agents)


@pytest.mark.parametrize('mode',['unaided','aisle','space'])
def test_information_modes_preserve_physical_routing_and_full_lot_deadline(mode):
    model=small(mode);a=next(iter(model.agents))
    model.run_until_complete()
    for p,q in zip(a.path,a.path[1:]):
        midpoint=((p[0]+q[0])/2,(p[1]+q[1])/2)
        assert min(math.dist(midpoint,foot) for _,_,foot in model.navigation._anchors(midpoint))<1e-6
    full=small(mode)
    for sid in ('far_1','far_2'):full.resource_manager.claim_space('background',sid)
    full.run_until_complete()
    assert all(a.state==DriverState.ABANDONED and a.search_time_s==600 for a in full.agents)


@pytest.mark.parametrize('mode',['aisle','space'])
def test_new_information_modes_are_repeatable_and_output_cadence_invariant(mode):
    facility=generate_synthetic_facility(38);pop=make_population(facility,size=8,seed=38)
    signatures=[]
    for cadence in (5,30):
        model=ParkingModel(facility,pop,seed=38,information_mode=mode,step_seconds=cadence,initial_occupancy_rate=.8)
        model.run_until_complete()
        signatures.append([(a.driver_id,a.chosen_space_id,a.parking_time_s,a.search_time_s,tuple(a.path)) for a in sorted(model.agents,key=lambda a:a.driver_id)])
    assert signatures[0]==signatures[1]


def test_aisle_mapping_covers_every_stall_once_and_mode_does_not_resample_population():
    facility=generate_synthetic_facility(38);pop=make_population(facility,size=3,seed=38)
    occupied=[]
    for mode in ('unaided','aisle','space'):
        model=ParkingModel(facility,pop,seed=38,information_mode=mode)
        assert model.population is pop
        ids=[sid for values in model.navigation.aisle_spaces.values() for sid in values]
        assert len(ids)==len(set(ids))==len(facility.spaces)
        assert set(ids)==set(model.navigation.space_aisle)
        occupied.append({sid for sid,s in model.space_states.items() if s.occupied})
    assert occupied[0]==occupied[1]==occupied[2]


def test_invalid_information_mode_is_rejected():
    with pytest.raises(ValueError,match='Information mode'):small('future_oracle')
