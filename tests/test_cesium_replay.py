"""The dashboard recorder must preserve the headless model's outcomes."""
import math
import pytest
from panda_abm.twin.replay import record_run,validate_settings,LiveSimulation
from panda_abm.behavior.continuous import make_population
from panda_abm.core.model import ParkingModel
from panda_abm.environment import load_facility_from_lot_config
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('settings',[{'occupancy':float('nan')},{'population_size':True},
                                    {'population_size':10000},{'arrival_interval_s':.5},
                                    {'model':'unimplemented'},{'information':'prediction'},{'unexpected':1}])
def test_reject_invalid_dashboard_scenarios(settings):
    with pytest.raises(ValueError):validate_settings(settings)


def test_replay_sampling_does_not_change_headless_decisions():
    settings=dict(seed=51,population_size=3,occupancy=.8,model='cpt',information='space',arrival_interval_s=20)
    replay=record_run(settings)
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    population=make_population(facility,size=3,seed=51)
    model=ParkingModel(facility,population,'cpt',seed=51,initial_occupancy_rate=.8,
                       information_mode='space',scenario_id='occupancy_0.8',run_id='information_51_0.8',
                       replication_id='seed_51',decision_seed_namespace='information_matched')
    model.run_until_complete()
    expected={a.driver_id:(a.chosen_space_id,a.search_time_s,a.parking_time_s,a.search_distance_m) for a in model.agents}
    for outcome in replay['outcomes']:
        assert (outcome['chosen_space'],outcome['search_s'],outcome['parking_time_s'],outcome['search_distance_m'])==expected[outcome['driver']]
    occupied=set(replay['initial_occupied'])
    for _,added,removed in replay['occupancy_changes']:
        assert not occupied.intersection(added)
        assert set(removed)<=occupied
        occupied.update(added);occupied.difference_update(removed)
    assert occupied==set(replay['initial_occupied'])
    for track in replay['tracks']:
        times=[row[0] for row in track['samples']]
        assert times==sorted(set(times))
        assert all(math.isfinite(v) for row in track['samples'] for v in row[1:3])
    assert replay['summary']['parked']+replay['summary']['abandoned']==3


def test_live_updates_preserve_recorded_run_and_release_balance():
    settings=dict(seed=51,population_size=3,occupancy=.8,model='cpt',information='space',arrival_interval_s=20)
    replay=record_run(settings)
    live=LiveSimulation(settings)
    description=live.describe()
    occupied=set(description['initial_occupied'])
    times=[]
    while not live.done:
        update=live.advance(120)
        for frame in update['frames']:
            times.append(frame['time_s'])
            assert not occupied.intersection(frame['added'])
            assert set(frame['removed'])<=occupied
            occupied.update(frame['added']);occupied.difference_update(frame['removed'])
            assert len(occupied)==frame['system'][1]
    assert update['summary']==replay['summary']
    assert occupied==set(replay['initial_occupied'])
    assert times==list(range(1,int(update['time_s'])+1))
    assert [(a.driver_id,a.chosen_space_id,a.search_time_s) for a in live.agents]==[(o['driver'],o['chosen_space'],o['search_s']) for o in replay['outcomes']]
    assert live.advance(10)['frames']==[]


@pytest.mark.parametrize('seconds',[0,121,True,1.5])
def test_live_step_bounds(seconds):
    live=LiveSimulation(dict(population_size=1))
    with pytest.raises(ValueError):live.advance(seconds)
