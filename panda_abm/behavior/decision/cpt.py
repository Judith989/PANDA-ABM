"""Finite-outcome CPT: ranked gains/losses and separate TK92 cumulative weights.
Parking prospect assumptions require calibration independently of the mathematics.
"""
import math
import numpy as np
from panda_abm.behavior.cpt_parameters import CPTParameters
from panda_abm.behavior.decision.base import CandidateEvaluation, DecisionResult
from panda_abm.behavior.decision.deterministic import DeterministicUtilityModel
from panda_abm.behavior.decision.transforms import linear_utility, stable_softmax

def cpt_value(delta,alpha=.88,beta=.88,lambda_loss=2.25):
    if not math.isfinite(delta): raise ValueError('Outcome must be finite')
    return float(delta**alpha if delta>=0 else -lambda_loss*(-delta)**beta)

def probability_weight(p,gamma=.61):
    """TK92 weighting function (not Prelec)."""
    if not math.isfinite(p) or not 0<=p<=1: raise ValueError('Probability must be within [0,1]')
    if not .28<=gamma<=1: raise ValueError('Weighting exponent must be in [0.28,1]')
    if p in (0.,1.): return float(p)
    return float(p**gamma/(p**gamma+(1-p)**gamma)**(1/gamma))

def cumulative_prospect_value(outcomes,parameters=None,reference=0.):
    """Evaluate (outcome, probability) pairs, merging ties before weighting.
    Gains use upper-tail weights; losses use lower-tail weights. Branch masses
    are not renormalized. Decision weights are not sampling probabilities.
    """
    cp=parameters or CPTParameters()
    if not math.isfinite(reference): raise ValueError('Reference must be finite')
    merged={};total=0.
    for outcome,p in outcomes:
        if not math.isfinite(outcome) or not math.isfinite(p) or not 0<=p<=1: raise ValueError('Invalid lottery')
        total+=p
        if p: merged[outcome-reference]=merged.get(outcome-reference,0.)+p
    if not math.isclose(total,1.,rel_tol=0,abs_tol=1e-10): raise ValueError('Lottery probabilities must sum to one')
    losses=sorted((x,p) for x,p in merged.items() if x<0)
    gains=sorted(((x,p) for x,p in merged.items() if x>=0),reverse=True)
    result=0.
    for branch,gamma in ((losses,cp.gamma_loss),(gains,cp.gamma)):
        cumulative=0.
        for x,p in branch:
            previous=cumulative;cumulative=min(1.,cumulative+p)
            weight=probability_weight(cumulative,gamma)-probability_weight(previous,gamma)
            result+=weight*cpt_value(x,cp.alpha,cp.beta,cp.lambda_loss)
    return float(result)

class CPTDecisionModel:
    model_name='cpt'
    def __init__(self,cpt_parameters=None): self.cpt_parameters=cpt_parameters
    def evaluate_candidates(self,context,candidates,perceived_state=None,forecast=None):
        base=DeterministicUtilityModel().evaluate_candidates(context,candidates,perceived_state,forecast)
        params=context.behavioral_parameters;refs=context.reference_points
        cp=self.cpt_parameters or context.cpt_parameters or CPTParameters()
        evaluations=[];future_offers=[]
        for item in base.candidate_evaluations:
            f=dict(item.features)
            reference=dict(f,walking_distance_m=refs.r_walk_m,search_time_s=refs.r_search_s,
                approach_time_s=0.,price_per_hour=0.,rule_risk=0.,availability_probability=1.,accessibility_match=0.,exit_distance_m=refs.r_exit_m)
            success=dict(f,search_time_s=context.accumulated_search_time_s+f['approach_time_s'],availability_probability=1.)
            reference_score=linear_utility(reference,params)
            success_score=linear_utility(success,params)
            good=success_score-reference_score
            # Both branches use the same oriented utility and reference. A
            # failed attempt obtains no parking-dependent benefit: walk/exit
            # scores are zero, availability/accessibility are zero. Price and
            # rule compliance remain neutral because no parking occurred.
            # This is a subjective failure proxy, not a calibrated terminal trip.
            failure=dict(success,walking_distance_m=250.,exit_distance_m=300.,
                accessibility_match=0.,availability_probability=0.,
                price_per_hour=0.,rule_risk=0.,
                search_time_s=success['search_time_s']+context.failure_delay_s)
            bad=linear_utility(failure,params)-reference_score
            p=f['availability_probability']
            value=cumulative_prospect_value(((good,p),(bad,1-p)),cp)
            reachable=context.remaining_search_time_s is None or f['approach_time_s']<context.remaining_search_time_s
            if item.feasible and reachable:
                # Transparent one-scan persistence forecast: a uniformly sampled
                # observed offer, attempted after one further scan. Both options
                # use terminal parking/failure outcomes and the same reference.
                delay=context.decision_interval_s
                later=dict(success,search_time_s=success['search_time_s']+delay)
                later_good=linear_utility(later,params)-reference_score
                later_failure=dict(failure,search_time_s=failure['search_time_s']+delay)
                later_bad=linear_utility(later_failure,params)-reference_score
                later_p=p
                if context.remaining_search_time_s is not None and delay+f['approach_time_s']>=context.remaining_search_time_s:
                    later_p=0.
                future_offers.append(((later_good,later_p),(later_bad,1-later_p)))
            diagnostics=dict(r_walk_m=refs.r_walk_m,r_search_s=refs.r_search_s,r_exit_m=refs.r_exit_m,
                alpha=cp.alpha,beta=cp.beta,lambda_loss=cp.lambda_loss,gamma=cp.gamma,gamma_loss=cp.gamma_loss,
                success_probability=p,success_outcome=good,failure_outcome=bad,cpt_value=value,
                success_utility=success_score,reference_utility=reference_score,
                failure_utility=linear_utility(failure,params),
                failure_search_time_s=failure['search_time_s'],
                walk_cpt_value=cpt_value((refs.r_walk_m-f['walking_distance_m'])/250.,cp.alpha,cp.beta,cp.lambda_loss),
                weighted_availability_probability=probability_weight(p,cp.gamma))
            evaluations.append(CandidateEvaluation(item.space_id,item.feasible and reachable,value,f,diagnostics))
        feasible=[e for e in evaluations if e.feasible]
        if not feasible: return DecisionResult('continue',None,None,tuple(evaluations),diagnostics={'reason':'no_feasible_candidates'})
        lottery=context.continuation_outcomes
        if lottery is None:
            lottery=tuple((outcome,probability/len(future_offers)) for offer in future_offers for outcome,probability in offer)
        continuation=cumulative_prospect_value(lottery,cp)
        for e in evaluations:
            e.diagnostics['continuation_value']=continuation
            e.diagnostics['continuation_from_observed_offers']=float(context.continuation_outcomes is None)
        aspiration_ok=[e for e in feasible if e.diagnostics['success_utility']>=params.acceptance_utility_threshold]
        if not aspiration_ok:
            return DecisionResult('continue',None,None,tuple(evaluations),diagnostics={'reason':'below_acceptance_threshold'})
        acceptable=[e for e in aspiration_ok if e.utility+1e-12>=continuation]
        if not acceptable:
            return DecisionResult('continue',None,None,tuple(evaluations),diagnostics={'reason':'continuation_preferred'})
        probabilities=stable_softmax(np.array([e.utility for e in acceptable]),params.decision_temperature)
        picked=acceptable[int(np.random.default_rng(context.rng_seed).choice(len(acceptable),p=probabilities))]
        probs={e.space_id:0. for e in feasible}
        probs.update({e.space_id:float(p) for e,p in zip(acceptable,probabilities)})
        return DecisionResult('park',picked.space_id,picked.utility,tuple(evaluations),probs,{'continuation_value':continuation})


class LinearProspectDecisionModel(CPTDecisionModel):
    """Matched CPT adapter control; change only the prospect transform."""
    model_name='linear_cpt'

    def __init__(self):
        super().__init__(CPTParameters(alpha=1,beta=1,lambda_loss=1,gamma=1,gamma_loss=1))
