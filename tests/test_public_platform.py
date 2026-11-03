import pytest
from panda_abm.twin.platform import simulate, compare, validate_comparison, interval
from panda_abm.twin.replay import record_run
import numpy as np


def test_compact_platform_preserves_recorded_decisions():
    settings=dict(population_size=3,seed=51,occupancy=.95,information='space',model='cpt')
    compact=simulate(settings);replay=record_run(settings)
    for actual,expected in zip(compact['outcomes'],replay['outcomes']):
        for key in actual:assert actual[key]==expected[key]
    assert compact['metrics']['search_s']==replay['summary']['mean_search_s']


def test_comparison_matches_inputs_and_retains_unsuccessful_drivers():
    data=compare(dict(settings=dict(population_size=3,seed=51,occupancy=1),models=['deterministic','cpt'],replications=1))
    assert len(data['runs'])==6
    assert len(data['populations'])==1
    assert len({r['population_sha256'] for r in data['runs']})==1
    assert len({r['initial_occupancy_sha256'] for r in data['runs']})==1
    assert all(len(r['outcomes'])==3 for r in data['runs'])
    assert all(r['metrics']['success_pct']==0 for r in data['runs'])
    assert all(e['metrics']['search_s']['mean']==0 for e in data['effects'])
    assert all(e['metrics']['joint_search_walk_s']['mean'] is None for e in data['effects'])
    assert all(e['metrics']['search_s']['low'] is None for e in data['effects'])


@pytest.mark.parametrize('payload',[
    {'replications':True},{'replications':31},{'replications':0},
    {'models':['cpt','cpt']},{'models':[]},{'models':['unknown']},
    {'settings':{'seed':2147483647},'replications':2},{'unexpected':1}])
def test_invalid_comparisons_are_rejected(payload):
    with pytest.raises(ValueError):validate_comparison(payload)


def test_intervals_resample_replications_and_handle_missing_data():
    assert interval([None],np.random.default_rng(1))['replications']==0
    result=interval([2,2,2],np.random.default_rng(1))
    assert result==dict(mean=2.,low=2.,high=2.,replications=3)
