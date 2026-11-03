"""Counterfactual panels and clustering null challenges for publication audit.

These test mathematical/structural behavior, not real human preference validity.
"""
from pathlib import Path
from dataclasses import replace
import json
import sys
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.continuous import sample_preferences,PopulationPriors
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.decision.cpt import CPTDecisionModel,CPTParameters,cumulative_prospect_value
from panda_abm.behavior.decision.random_utility import RandomUtilityModel
from panda_abm.behavior.decision.transforms import stable_softmax
from panda_abm.behavior.references import ReferencePoints
from panda_abm.environment import ParkingSpace
from panda_abm.analysis.profiles import explore_behavioral_regimes


def panel_audit(out):
    rng=np.random.default_rng(20261028); rows=[]; properties=[]
    linear=CPTParameters(alpha=1,beta=1,lambda_loss=1,gamma=1,gamma_loss=1)
    for i in range(2000):
        params=sample_preferences(rng,PopulationPriors())
        spaces=[ParkingSpace(str(j),'A',float(rng.uniform(0,250)),float(rng.uniform(0,100)),price_per_hour=float(rng.uniform(0,10))) for j in range(4)]
        ctx=DecisionContext('audit',params,ReferencePoints(r_walk_m=100,r_search_s=300),float(rng.uniform(0,500)),(0,0),(0,0),
            rng_seed=i,approach_times_s={s.space_id:float(rng.uniform(2,80)) for s in spaces},
            availability_probabilities={s.space_id:float(rng.uniform(.3,1)) for s in spaces},remaining_search_time_s=100)
        # Zero temperature approximates deterministic choice and makes the
        # mechanism changes inspectable without different noise realizations.
        ctx=replace(ctx,behavioral_parameters=replace(params,decision_temperature=1e-9))
        def cpt(c=ctx,cp=None,candidates=spaces): return CPTDecisionModel(cp).evaluate_candidates(c,candidates)
        baseline=cpt(); rum=RandomUtilityModel().evaluate_candidates(ctx,spaces)
        neutral=cpt(cp=linear)
        low=cpt(cp=CPTParameters(lambda_loss=1)); high=cpt(cp=CPTParameters(lambda_loss=4))
        rlow=cpt(replace(ctx,reference_points=replace(ctx.reference_points,r_search_s=150)))
        rhigh=cpt(replace(ctx,reference_points=replace(ctx.reference_points,r_search_s=450)))
        # Duplicate an existing offer under a new ID: the common offers keep
        # identical outcomes, while the uniform continuation mixture changes.
        duplicate=replace(spaces[-1],space_id='duplicate')
        dctx=replace(ctx,approach_times_s={**ctx.approach_times_s,'duplicate':ctx.approach_times_s['3']},
            availability_probabilities={**ctx.availability_probabilities,'duplicate':ctx.availability_probabilities['3']})
        duplicated=cpt(dctx,candidates=spaces+[duplicate])
        def decision(r): return r.chosen_action,r.chosen_space_id
        eligible=lambda r: tuple(e.space_id for e in r.candidate_evaluations if r.probabilities.get(e.space_id,0)>0)
        # Direct prospect ranking is independent of continuation acceptance.
        rank=lambda r: max(r.candidate_evaluations,key=lambda e:e.utility).space_id
        rows.append(dict(context=i,cpt_vs_rum=decision(baseline)!=decision(rum),
            linearized_adapter_vs_rum=decision(neutral)!=decision(rum),
            lambda_rank_changed=rank(low)!=rank(high),lambda_decision_changed=decision(low)!=decision(high),
            reference_rank_changed=rank(rlow)!=rank(rhigh),reference_decision_changed=decision(rlow)!=decision(rhigh),
            duplicate_common_acceptance_changed=eligible(baseline)!=tuple(s for s in eligible(duplicated) if s!='duplicate'),
            duplicate_continuation_delta=duplicated.diagnostics.get('continuation_value',0)-baseline.diagnostics.get('continuation_value',0)))
        # Draw finite arbitrary lotteries. Same probability coupling and all
        # improved outcomes imply strict first-order stochastic dominance.
        x=rng.uniform(-5,5,8);p=rng.dirichlet(np.ones(8));better=x+rng.uniform(.001,2,8)
        cp=CPTParameters(alpha=float(rng.uniform(.2,1)),beta=float(rng.uniform(.2,1)),lambda_loss=float(rng.uniform(.2,8)),
            gamma=float(rng.uniform(.28,1)),gamma_loss=float(rng.uniform(.28,1)))
        a=cumulative_prospect_value(tuple(zip(x,p)),cp);b=cumulative_prospect_value(tuple(zip(better,p)),cp)
        perm=rng.permutation(8)
        reordered=cumulative_prospect_value(tuple(zip(x[perm],p[perm])),cp)
        shifted=cumulative_prospect_value(tuple(zip(x+17,p)),cp,reference=17)
        expected=cumulative_prospect_value(tuple(zip(x,p)),linear)
        properties.append(dict(context=i,dominance=b>a,order_invariance=abs(a-reordered)<1e-10,
            reference_translation=abs(a-shifted)<1e-10,expected_value_limit=abs(expected-float(x@p))<1e-10))
    pd.DataFrame(rows).to_csv(out/'mechanism_panels.csv',index=False)
    pd.DataFrame(properties).to_csv(out/'lottery_properties.csv',index=False)
    # Exact scale non-identification of logit: theta/tau is identified, not
    # theta and tau separately. This does not prove CPT is unidentifiable.
    logits=np.array([.2,.8,1.1])
    scale_error=float(np.max(np.abs(stable_softmax(logits,.35)-stable_softmax(logits*4,1.4))))
    (out/'mechanism_summary.json').write_text(json.dumps(dict(contexts=len(rows),rates=pd.DataFrame(rows).drop(columns='context').mean().to_dict(),
        property_failures=(~pd.DataFrame(properties).drop(columns='context')).sum().to_dict(),
        rum_common_scale_probability_error=scale_error,
        caution='Artificial opportunities; zero-temperature mechanism screen. Neither observed behavior nor parameter recovery.'),indent=2))


def null_challenge(out):
    rows=[]
    for distribution in ('single_gaussian','single_skewed','curved_continuum','two_separated_groups'):
        for replicate in range(20):
            rng=np.random.default_rng(50100+replicate)
            n=600;z=rng.normal(size=(n,2))
            if distribution=='single_gaussian': x=np.column_stack((4+.35*z[:,0],.7+.08*z[:,1]))
            elif distribution=='single_skewed': x=np.column_stack((3+.5*rng.gamma(2,1,n),.3+.15*rng.gamma(2,1,n)))
            elif distribution=='curved_continuum': x=np.column_stack((4+.4*z[:,0],.5+.15*z[:,0]**2+.05*z[:,1]))
            else:
                group=rng.integers(2,size=n);x=np.column_stack((3+2*group+.15*z[:,0],.3+.7*group+.04*z[:,1]))
            frame=pd.DataFrame(dict(seed=np.repeat(np.arange(10),60),search_s=np.expm1(x[:,0]),walk_relative=np.expm1(x[:,1])))
            result,_,_=explore_behavioral_regimes(frame,range(6),range(6,10),n_init=5,bootstrap_repetitions=20)
            rows.append(dict(distribution=distribution,replicate=replicate,**result))
        print(distribution+' complete',flush=True)
    pd.DataFrame(rows).to_csv(out/'profile_null_challenge.csv',index=False)
    summary=pd.DataFrame(rows).groupby('distribution').agg(replicates=('replicate','size'),
        density_gate_passes=('candidate_supported','sum'),mean_components=('selected_components','mean'))
    summary.to_csv(out/'profile_null_summary.csv')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/publication_audit_20261027')
    out=parser.parse_args().output;out.mkdir(parents=True,exist_ok=True)
    if (out/'mechanism_design.json').exists():raise FileExistsError('Preserve frozen mechanism design')
    (out/'mechanism_design.json').write_text(json.dumps(dict(seed=20261028,panels=2000,lotteries=2000,
        null_replicates=20,null_sample=600,train_seeds=list(range(6)),test_seeds=list(range(6,10)),
        bootstrap_refits=20,interpretation='A Gaussian mixture may fit continuous non-Gaussian densities. Passing gates must not imply latent classes.'),indent=2))
    panel_audit(out);print('mechanism panels complete',flush=True);null_challenge(out)
