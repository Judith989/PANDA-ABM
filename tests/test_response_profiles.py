import numpy as np
import pytest
pytest.importorskip('sklearn')
from panda_abm.analysis.response_profiles import final_action_probabilities,response_fingerprint,fit_profiles
from panda_abm.behavior.decision.base import DecisionResult,CandidateEvaluation
from panda_abm.behavior.population import DriverAttributes,DriverSpec
from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.cpt_parameters import CPTParameters

def test_m1_rejected_probability_is_continue_not_success():
    items=tuple(CandidateEvaluation(f's{i}',True,u) for i,u in enumerate([2.,1.,3.]))
    result=DecisionResult('continue',None,None,items,{'s0':.2,'s1':.3,'s2':.5})
    np.testing.assert_allclose(final_action_probabilities(result,'rum',1.75),[.2,0,.5,.3])

@pytest.mark.parametrize('model',['deterministic','rum','cpt'])
def test_probes_include_constrained_drivers_and_are_rng_independent(model):
    d=DriverSpec(DriverAttributes('x',0,0,mobility_limitation=True,max_walking_distance_m=50.),
        BehavioralParameters(),ReferencePoints(),CPTParameters())
    a=response_fingerprint(d,model);b=response_fingerprint(d,model)
    np.testing.assert_array_equal(a,b)
    assert a.shape==(48,) and (a>=0).all()
    np.testing.assert_allclose(a.reshape(-1,4).sum(axis=1),1.)
    # No eligible/permit spaces and the regular offer exceeds the walking cap.
    np.testing.assert_array_equal(a[-12:].reshape(3,4)[:,3],1.)

def test_one_group_allowed_and_validation_cannot_change_discovery():
    rng=np.random.default_rng(9);seeds=np.repeat(np.arange(10),30)
    p=np.exp(rng.normal(0,.04,(300,4)));p/=p.sum(axis=1,keepdims=True)
    x=np.hstack([p,p]);changed=x.copy();changed[seeds>=6]=np.roll(changed[seeds>=6],1,axis=1)
    a,ga,_,sa,_=fit_profiles(x,seeds,range(6),range(6,10),bootstrap=2,n_init=2,max_components=2)
    b,gb,_,sb,_=fit_profiles(changed,seeds,range(6),range(6,10),bootstrap=2,n_init=2,max_components=2)
    assert a['components']==1 and not a['supported']
    np.testing.assert_allclose([r['bic'] for r in sa],[r['bic'] for r in sb])
    np.testing.assert_array_equal(ga[seeds<6],gb[seeds<6])
