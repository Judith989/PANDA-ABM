"""Exact observation windows, censoring, prefix consistency and resumed execution."""
import pytest
from panda_abm.twin.replay import LiveSimulation, record_run, validate_settings
from panda_abm.twin.platform import simulate, compare


@pytest.mark.parametrize('duration',[True,0,9,21601,60.5,'600'])
def test_reject_invalid_duration(duration):
    with pytest.raises(ValueError):validate_settings(dict(simulation_duration_s=duration))


def test_cutoff_retains_unfinished_and_not_arrived_drivers():
    settings=dict(population_size=4,initial_free_count=0,simulation_duration_s=60)
    replay=record_run(settings)
    summary=replay['summary']
    assert replay['duration_s']==60
    assert summary['arrivals']==3 and summary['not_arrived']==1
    assert summary['unfinished']==3 and summary['abandoned']==0
    assert summary['mean_search_s']==40
    assert [o['search_s'] for o in replay['outcomes']]==[60,40,20,0]
    assert [o['right_censored'] for o in replay['outcomes']]==[True,True,True,False]
    assert replay['outcomes'][-1]['success'] is None
    assert replay['termination_reason']=='time_limit'
    compact=simulate(settings)
    assert compact['window_summary']==summary
    assert compact['metrics']['search_s']==40 and compact['metrics']['success_pct']==0
    for actual,expected in zip(compact['outcomes'],replay['outcomes']):
        assert all(actual[k]==expected[k] for k in actual)


def test_live_chunks_resume_same_run_and_stop_exactly_at_limit():
    settings=dict(population_size=4,initial_free_count=0,simulation_duration_s=60,traffic_enabled=True)
    live=LiveSimulation(settings)
    first=live.advance(17)
    assert first['time_s']==17 and not first['complete']
    identity=id(live.model)
    for _ in range(3):assert live.frame()['time_s']==17
    end=live.advance(120)
    assert end['time_s']==60 and end['complete'] and id(live.model)==identity
    assert end['summary']==record_run(settings)['summary']
    assert end['cutoff_statuses']['D0003']['search_status']=='not_arrived'
    assert live.advance(120)['frames']==[] and live.model.clock_s==60


def test_longer_window_does_not_change_earlier_decisions_or_trajectories():
    settings=dict(population_size=3,occupancy=.8,information='space',model='rum',seed=51)
    short=record_run(settings|dict(simulation_duration_s=60))
    long=record_run(settings|dict(simulation_duration_s=120))
    assert short['initial_occupied']==long['initial_occupied']
    assert short['population']==long['population']
    for a,b in zip(short['tracks'],long['tracks']):
        assert a['samples']==[r for r in b['samples'] if r[0]<=60]


def test_window_runs_scheduled_events_even_after_drivers_have_finished():
    live=LiveSimulation(dict(population_size=1,initial_free_count=0,simulation_duration_s=60))
    live.model.max_search_time_s=10
    sid=live.initial_occupied[0]
    live.model.scheduled_interventions=[dict(time_s=40,action='release',space_ids=[sid])]
    end=live.advance(120)
    assert end['time_s']==60 and end['summary']['abandoned']==1
    assert live.model.resource_manager.is_available(sid)


def test_matched_comparisons_share_cutoff_cohort_and_inputs():
    data=compare(dict(settings=dict(population_size=4,initial_free_count=0,simulation_duration_s=60),models=['cpt'],replications=1))
    assert len(data['runs'])==3
    assert all(r['simulated_duration_s']==60 for r in data['runs'])
    assert all(r['window_summary']['arrivals']==3 for r in data['runs'])
    assert len({r['initial_occupancy_sha256'] for r in data['runs']})==1
