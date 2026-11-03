import numpy as np
import pandas as pd
import pytest
pytest.importorskip('sklearn')
from panda_abm.analysis.profiles import explore_behavioral_regimes


def frame(two_groups):
    rng=np.random.default_rng(8)
    seed=np.repeat(np.arange(10),80)
    x=rng.normal(0,.15,size=(len(seed),2))
    if two_groups:x+=np.where((np.arange(len(seed))%2)[:,None]==0,[2,.6],[4,1.4])
    else:x+=[3,1]
    return pd.DataFrame({'seed':seed,'search_s':np.expm1(x[:,0]),'walk_relative':np.expm1(x[:,1])})


def test_one_population_is_allowed_to_have_no_discrete_profiles():
    result,assignments,selection=explore_behavioral_regimes(frame(False),range(6),range(6,10),max_components=3,n_init=3,bootstrap_repetitions=2)
    assert result['selected_components']==1
    assert not result['candidate_supported']
    assert len(assignments)==800


def test_separated_behavioral_groups_can_be_detected_without_persona_inputs():
    result,assignments,selection=explore_behavioral_regimes(frame(True),range(6),range(6,10),max_components=3,n_init=3,bootstrap_repetitions=3)
    assert result['selected_components']==2
    assert result['candidate_supported']
    assert result['min_bootstrap_jaccard']>.9


def test_validation_outcomes_cannot_change_training_model_selection():
    original=frame(False);perturbed=original.copy()
    perturbed.loc[perturbed.seed>=6,'search_s']*=10
    a,_,sa=explore_behavioral_regimes(original,range(6),range(6,10),max_components=2,n_init=2,bootstrap_repetitions=1)
    b,_,sb=explore_behavioral_regimes(perturbed,range(6),range(6,10),max_components=2,n_init=2,bootstrap_repetitions=1)
    assert sa.bic.tolist()==sb.bic.tolist()
