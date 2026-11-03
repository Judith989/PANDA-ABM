"""Paired driver outcomes and identical-information decision-model comparisons.

Does not modify production models. Replays observed M0 decision contexts using
common random seeds, and repeats with response temperature zero to isolate rank.
"""
from pathlib import Path
from dataclasses import replace
import argparse
import json
import math
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.behavior.decision import DeterministicUtilityModel,RandomUtilityModel,CPTDecisionModel
from panda_abm.core.model import ParkingModel
from panda_abm.environment import load_facility_from_lot_config,generate_synthetic_facility

MODELS={'deterministic':DeterministicUtilityModel,'rum':RandomUtilityModel,'cpt':CPTDecisionModel}


def paired_outcomes(source,output,facility):
    drivers=pd.read_csv(source/'drivers.csv')
    parts=[]
    for other in ('deterministic','rum'):
        a=drivers[drivers.model=='cpt'];b=drivers[drivers.model==other]
        joined=a.merge(b,on=['scenario','seed','driver','persona'],suffixes=('_cpt','_other'),validate='one_to_one')
        assert len(joined)==len(a)
        joined['comparison']='cpt_vs_'+other
        joined['both_parked']=joined.success_cpt & joined.success_other
        joined['same_outcome']=joined.success_cpt==joined.success_other
        # Abandonment/NaN targets must not count as identical parked spaces.
        joined['same_space']=joined.both_parked & (joined.chosen_space_cpt==joined.chosen_space_other)
        joined['walk_delta_m']=joined.walking_distance_m_cpt-joined.walking_distance_m_other
        joined['search_delta_s']=joined.search_time_s_cpt-joined.search_time_s_other
        joined['exit_delta_m']=joined.preferred_exit_distance_m_cpt-joined.preferred_exit_distance_m_other
        distances=[]
        for r in joined.itertuples():
            if not r.both_parked:distances.append(np.nan);continue
            spaces=facility.space_by_id if r.scenario.startswith('walmart') else generate_synthetic_facility(r.seed).space_by_id
            x,y=spaces[r.chosen_space_cpt],spaces[r.chosen_space_other]
            distances.append(math.dist((x.x_m,x.y_m),(y.x_m,y.y_m)))
        joined['chosen_space_separation_m']=distances
        parts.append(joined)
    paired=pd.concat(parts,ignore_index=True);paired.to_csv(output/'paired_drivers.csv',index=False)
    rows=[]
    for key,g in paired.groupby(['scenario','persona','comparison']):
        parked=g[g.both_parked]
        rows.append(dict(zip(['scenario','persona','comparison'],key),drivers=len(g),both_parked=len(parked),
            cpt_parked=int(g.success_cpt.sum()),other_parked=int(g.success_other.sum()),
            same_outcome_rate=g.same_outcome.mean(),same_space_rate_both=parked.same_space.mean(),
            median_space_separation_m=parked.chosen_space_separation_m.median(),
            mean_abs_walk_delta_m=parked.walk_delta_m.abs().mean(),mean_walk_delta_m=parked.walk_delta_m.mean(),
            mean_abs_search_delta_s=g.search_delta_s.abs().mean(),mean_search_delta_s=g.search_delta_s.mean(),
            mean_abs_exit_delta_m=parked.exit_delta_m.abs().mean()))
    pd.DataFrame(rows).to_csv(output/'paired_by_persona.csv',index=False)
    return paired


class Recorder:
    model_name='deterministic'
    def __init__(self):self.snapshots=[];self.counts={};self.base=DeterministicUtilityModel()
    def evaluate_candidates(self,context,candidates,*args,**kwargs):
        # First three nonempty observations per driver. This avoids allowing a
        # repeatedly rejecting driver to dominate the snapshot comparison.
        if candidates and self.counts.get(context.driver_id,0)<3:
            self.snapshots.append((context,tuple(candidates)))
            self.counts[context.driver_id]=self.counts.get(context.driver_id,0)+1
        return self.base.evaluate_candidates(context,candidates,*args,**kwargs)


def probability_vector(result,space_ids,threshold):
    vector=np.zeros(len(space_ids)+1)
    if result.probabilities:
        evaluations={e.space_id:e for e in result.candidate_evaluations}
        for i,sid in enumerate(space_ids):
            p=result.probabilities.get(sid,0.)
            e=evaluations[sid]
            # RUM gates after sampling: failed aspiration mass belongs to
            # continuing, regardless of this particular sampled action.
            if e.diagnostics.get('success_utility',e.utility)>=threshold:vector[i]=p
            else:vector[-1]+=p
    elif result.chosen_action=='continue':vector[-1]=1
    else:vector[space_ids.index(result.chosen_space_id)]=1
    assert abs(vector.sum()-1)<1e-9
    return vector


def replay(output,facility):
    rows=[]
    scenarios=[('walmart_crowded',.8,80,False),('walmart_saturated',.95,80,False),
               ('walmart_saturated_exit_preference',.95,80,True),('synthetic_rule_tradeoff',.35,40,False)]
    for scenario,occupancy,size,exit_preference in scenarios:
        for seed in (42,43,44):
            f=facility if scenario.startswith('walmart') else generate_synthetic_facility(seed)
            illegal=scenario=='synthetic_rule_tradeoff'
            if illegal:f=replace(f,spaces=tuple(replace(s,price_per_hour=0. if s.accessible or s.reserved_type else 9.) for s in f.spaces))
            pop=make_population(f,size=size,seed=seed,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
            if exit_preference:pop=replace(pop,drivers=tuple(replace(d,behavioral_parameters=replace(d.behavioral_parameters,beta_exit=1.)) for d in pop.drivers))
            personas={d.driver_id:d.attributes.persona for d in pop.drivers}
            recorder=Recorder()
            model=ParkingModel(f,pop,decision_model=recorder,seed=seed,initial_occupancy_rate=occupancy,
                run_id=f'{scenario}_deterministic_{seed}',scenario_id=scenario,allow_illegal_alternatives=illegal)
            model.run_until_complete()
            for index,(ctx,candidates) in enumerate(recorder.snapshots):
                ids=[s.space_id for s in candidates]
                # All models receive identical seed, candidates, context and
                # claim forecasts. No model name is mixed into replay RNG.
                ctx=replace(ctx,rng_seed=seed*100000+index)
                results={name:cls().evaluate_candidates(ctx,list(candidates)) for name,cls in MODELS.items()}
                no_noise=replace(ctx,behavioral_parameters=replace(ctx.behavioral_parameters,decision_temperature=0))
                zero={name:cls().evaluate_candidates(no_noise,list(candidates)) for name,cls in MODELS.items()}
                cpt=results['cpt'];base=results['deterministic']
                scores={e.space_id:e.utility for e in base.candidate_evaluations if e.feasible}
                cscores={e.space_id:e.utility for e in cpt.candidate_evaluations if e.feasible}
                common=sorted(scores.keys() & cscores.keys())
                # Compare all pairwise orderings; ties are counted separately.
                comparable=0;reversals=0
                for i,a in enumerate(common):
                    for b in common[i+1:]:
                        x=scores[a]-scores[b];y=cscores[a]-cscores[b]
                        if abs(x)>1e-10 and abs(y)>1e-10:
                            comparable+=1;reversals+=x*y<0
                for other in ('deterministic','rum'):
                    result=results[other]
                    row=dict(scenario=scenario,seed=seed,snapshot=index,driver=ctx.driver_id,
                        persona=personas[ctx.driver_id],candidates=len(candidates),multi_choice=len(common)>1,
                        comparison='cpt_vs_'+other,
                        same_action=cpt.chosen_action==result.chosen_action,
                        same_choice=(cpt.chosen_action,cpt.chosen_space_id)==(result.chosen_action,result.chosen_space_id),
                        zero_noise_same_choice=(zero['cpt'].chosen_action,zero['cpt'].chosen_space_id)==(zero[other].chosen_action,zero[other].chosen_space_id),
                        probability_tv=float(abs(probability_vector(cpt,ids,ctx.behavioral_parameters.acceptance_utility_threshold)-probability_vector(result,ids,ctx.behavioral_parameters.acceptance_utility_threshold)).sum()/2),
                        ranking_pairs=comparable,ranking_reversals=int(reversals),
                        cpt_choice=cpt.chosen_space_id,other_choice=result.chosen_space_id,
                        cpt_action=cpt.chosen_action,other_action=result.chosen_action)
                    rows.append(row)
            pd.DataFrame(rows).to_csv(output/'replay_decisions.csv',index=False)
            print(f'{scenario} seed {seed}: {len(recorder.snapshots)} identical-information contexts',flush=True)
    frame=pd.DataFrame(rows)
    summary=frame.groupby(['scenario','persona','comparison','multi_choice']).agg(
        decisions=('driver','count'),same_action_rate=('same_action','mean'),same_choice_rate=('same_choice','mean'),
        zero_noise_same_choice_rate=('zero_noise_same_choice','mean'),mean_probability_tv=('probability_tv','mean'),
        ranking_pairs=('ranking_pairs','sum'),ranking_reversals=('ranking_reversals','sum')).reset_index()
    summary.to_csv(output/'replay_by_persona.csv',index=False)
    return frame


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/model_distinctness_20261027')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    paired=paired_outcomes(ROOT/'results/cpt_continuation_20261027/stress',args.output,facility)
    print('Paired outcomes ready',flush=True)
    replay(args.output,facility)
    (args.output/'conditions.json').write_text(json.dumps(dict(seeds=[42,43,44],
        source='results/cpt_continuation_20261027/stress',snapshot_source='M0 trajectories, first three nonempty contexts per driver',
        common_random_numbers=True,zero_temperature_control=True,production_models_modified=False),indent=2)+'\n')


if __name__=='__main__':main()
