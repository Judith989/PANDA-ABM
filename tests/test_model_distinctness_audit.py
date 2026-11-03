import pytest
from scripts.audit_model_distinctness import probability_vector
from panda_abm.behavior.decision.base import CandidateEvaluation,DecisionResult


@pytest.mark.parametrize('sampled_action',['park','continue'])
def test_audit_assigns_rum_rejection_probability_to_continue_independent_of_sample(sampled_action):
    result=DecisionResult(sampled_action,'good' if sampled_action=='park' else None,None,
        (CandidateEvaluation('good',True,2.),CandidateEvaluation('poor',True,1.)),
        {'good':.6,'poor':.4})
    assert probability_vector(result,['good','poor'],1.75)==pytest.approx([.6,0,.4])


def test_audit_assigns_deterministic_continue_to_outside_option():
    result=DecisionResult('continue',None,None,())
    assert probability_vector(result,['a','b'],1.75)==pytest.approx([0,0,1])
