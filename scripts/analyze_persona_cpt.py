"""Paired seed-cluster summaries and frozen CPT sensitivity comparisons."""
from pathlib import Path
from dataclasses import replace
import argparse
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior import BehavioralParameters,ReferencePoints
from panda_abm.behavior.cpt_parameters import CPTParameters,PERSONA_CPT_PROFILES
from panda_abm.behavior.decision import CPTDecisionModel,DecisionContext,DeterministicUtilityModel,RandomUtilityModel
from panda_abm.environment import ParkingSpace
from scripts.audit_model_distinctness import probability_vector


def choice(result):return result.chosen_action,result.chosen_space_id


def decode(record):
    values=record['context'].copy()
    values['behavioral_parameters']=BehavioralParameters(**values['behavioral_parameters'])
    values['reference_points']=ReferencePoints(**values['reference_points'])
    cp=values.get('cpt_parameters')
    values['cpt_parameters']=CPTParameters(**cp) if cp else None
    return DecisionContext(**values),[ParkingSpace(**s) for s in record['candidates']]


def dynamic(out):
    df=pd.read_csv(out/'drivers.csv')
    joined=df[df.arm=='shared'].merge(df[df.arm=='persona'],on=['scenario','seed','driver','persona'],suffixes=('_shared','_persona'),validate='one_to_one')
    assert len(joined)*2==len(df)
    joined['both_parked']=joined.success_shared & joined.success_persona
    joined['same_space']=joined.both_parked & (joined.chosen_space_shared==joined.chosen_space_persona)
    joined.to_csv(out/'paired_drivers.csv',index=False)
    records=[];rng=np.random.default_rng(27102026)
    for key,g in joined.groupby(['scenario','persona']):
        both=g[g.both_parked]
        seeds=g.groupby('seed')
        success=seeds.apply(lambda x:float(x.success_persona.mean()-x.success_shared.mean()),include_groups=False)
        search=seeds.apply(lambda x:float((x.search_s_persona-x.search_s_shared).mean()),include_groups=False)
        index=rng.integers(0,len(success),size=(5000,len(success)))
        success_ci=np.quantile(success.to_numpy()[index].mean(axis=1),[.025,.975])
        search_ci=np.quantile(search.to_numpy()[index].mean(axis=1),[.025,.975])
        records.append(dict(scenario=key[0],persona=key[1],seeds=len(success),drivers=len(g),
            parked_shared=int(g.success_shared.sum()),parked_persona=int(g.success_persona.sum()),
            success_delta=success.mean(),success_ci_low=success_ci[0],success_ci_high=success_ci[1],
            search_delta_s=search.mean(),search_ci_low=search_ci[0],search_ci_high=search_ci[1],
            jointly_parked=len(both),same_space_fraction=both.same_space.mean(),
            walk_delta_m=(both.walk_m_persona-both.walk_m_shared).mean(),
            claim_probability_delta=(both.claim_probability_persona-both.claim_probability_shared).mean()))
    summary=pd.DataFrame(records);summary.to_csv(out/'paired_persona_summary.csv',index=False)
    checks=json.loads((out/'checks.json').read_text())
    assert len(checks)==len(json.loads((out/'design.json').read_text())['seeds'])*6
    assert all(all(v for k,v in r.items() if k not in ('scenario','seed','arm')) for r in checks)
    return summary


def replay(out):
    rows=[];sensitivity=[];oat=[];seen={}
    with (out/'replay_contexts.jsonl').open(encoding='utf-8') as handle:
        for line in handle:
            record=json.loads(line);ctx,candidates=decode(record)
            ctx=replace(ctx,rng_seed=record['seed']*100000+record['snapshot'])
            cp=PERSONA_CPT_PROFILES[record['persona']]
            common=dict(scenario=record['scenario'],seed=record['seed'],snapshot=record['snapshot'],persona=record['persona'],driver=ctx.driver_id)
            shared=CPTDecisionModel(CPTParameters()).evaluate_candidates(ctx,candidates)
            persona=CPTDecisionModel(cp).evaluate_candidates(ctx,candidates)
            noisy_baselines={name:cls().evaluate_candidates(ctx,candidates) for name,cls in [('m0',DeterministicUtilityModel),('m1',RandomUtilityModel)]}
            no_noise=replace(ctx,behavioral_parameters=replace(ctx.behavioral_parameters,decision_temperature=0))
            zshared=CPTDecisionModel(CPTParameters()).evaluate_candidates(no_noise,candidates)
            zpersona=CPTDecisionModel(cp).evaluate_candidates(no_noise,candidates)
            zm0=DeterministicUtilityModel().evaluate_candidates(no_noise,candidates)
            ids=[s.space_id for s in candidates];threshold=ctx.behavioral_parameters.acceptance_utility_threshold
            multi=sum(e.feasible for e in shared.candidate_evaluations)>1
            if record['persona']!='risk_averse':assert shared==persona and zshared==zpersona
            rows.append(dict(**common,multi=multi,profile_changed_choice=choice(shared)!=choice(persona),
                zero_noise_changed_choice=choice(zshared)!=choice(zpersona),
                shared_differs_m0=choice(zshared)!=choice(zm0),persona_differs_m0=choice(zpersona)!=choice(zm0),
                profile_probability_tv=float(abs(probability_vector(shared,ids,threshold)-probability_vector(persona,ids,threshold)).sum()/2),
                shared_choice=shared.chosen_space_id,persona_choice=persona.chosen_space_id,
                shared_vs_m1_same=choice(shared)==choice(noisy_baselines['m1']),persona_vs_m1_same=choice(persona)==choice(noisy_baselines['m1'])))
            # Outcome-independent balanced subset for the larger factorial grid.
            group=(record['scenario'],record['seed'],record['persona'])
            if not multi or seen.get(group,0)>=2:continue
            seen[group]=seen.get(group,0)+1
            for hazard in (0,.5,1,2):
                probabilities={sid:(1. if hazard==0 else p**hazard) for sid,p in ctx.availability_probabilities.items()}
                for reference in (.75,1,1.25):
                    expected_walk=ctx.reference_points.r_walk_m*reference
                    if ctx.max_walking_distance_m is not None:expected_walk=min(expected_walk,ctx.max_walking_distance_m)
                    control=replace(no_noise,availability_probabilities=probabilities,reference_points=replace(ctx.reference_points,r_walk_m=expected_walk))
                    base=CPTDecisionModel(CPTParameters()).evaluate_candidates(control,candidates)
                    for loss in (1,1.6,2.25,3,4):
                        result=CPTDecisionModel(CPTParameters(lambda_loss=loss)).evaluate_candidates(control,candidates)
                        sensitivity.append(dict(**common,hazard_multiplier=hazard,reference_multiplier=reference,lambda_loss=loss,
                            changed_choice=choice(result)!=choice(base),choice=result.chosen_space_id,action=result.chosen_action))
            variants=[]
            for name,values in [('alpha',(.7,.88,1)),('beta',(.7,.88,1)),('gamma',(.5,.7,.9,1)),('gamma_loss',(.5,.7,.9,1))]:
                variants.extend((name,value,replace(cp,**{name:value})) for value in values)
            for name,value,variant in variants:
                a=CPTDecisionModel(replace(variant,lambda_loss=2.25)).evaluate_candidates(no_noise,candidates)
                b=CPTDecisionModel(variant).evaluate_candidates(no_noise,candidates)
                oat.append(dict(**common,parameter=name,value=value,changed_choice=choice(a)!=choice(b)))
            for temperature in (0,.175,.35,.7):
                control=replace(ctx,behavioral_parameters=replace(ctx.behavioral_parameters,decision_temperature=temperature))
                a=CPTDecisionModel(CPTParameters()).evaluate_candidates(control,candidates)
                b=CPTDecisionModel(cp).evaluate_candidates(control,candidates)
                oat.append(dict(**common,parameter='temperature',value=temperature,changed_choice=choice(a)!=choice(b)))
            # Outcome-unit sensitivity scales all generalized utility weights,
            # aspiration and response temperature together, preserving M0 units.
            weight_names=[name for name in ctx.behavioral_parameters.__dataclass_fields__ if name.startswith('beta_')]
            for scale in (.5,1,2):
                changes={name:getattr(ctx.behavioral_parameters,name)*scale for name in weight_names}
                changes.update(decision_temperature=ctx.behavioral_parameters.decision_temperature*scale,
                    acceptance_utility_threshold=ctx.behavioral_parameters.acceptance_utility_threshold*scale)
                control=replace(ctx,behavioral_parameters=replace(ctx.behavioral_parameters,**changes))
                a=CPTDecisionModel(CPTParameters()).evaluate_candidates(control,candidates)
                b=CPTDecisionModel(cp).evaluate_candidates(control,candidates)
                oat.append(dict(**common,parameter='outcome_scale',value=scale,changed_choice=choice(a)!=choice(b)))
    frame=pd.DataFrame(rows);frame.to_csv(out/'replay_comparisons.csv',index=False)
    frame[frame.multi].groupby(['scenario','persona']).agg(contexts=('driver','count'),
        profile_changed_choice=('profile_changed_choice','mean'),zero_noise_changed_choice=('zero_noise_changed_choice','mean'),
        profile_probability_tv=('profile_probability_tv','mean'),shared_differs_m0=('shared_differs_m0','mean'),persona_differs_m0=('persona_differs_m0','mean')).reset_index().to_csv(out/'replay_summary.csv',index=False)
    sensitivity=pd.DataFrame(sensitivity);sensitivity.to_csv(out/'sensitivity_decisions.csv',index=False)
    sensitivity.groupby(['persona','hazard_multiplier','reference_multiplier','lambda_loss']).agg(contexts=('driver','count'),changed_choice=('changed_choice','mean')).reset_index().to_csv(out/'sensitivity_summary.csv',index=False)
    oat=pd.DataFrame(oat);oat.to_csv(out/'oat_decisions.csv',index=False)
    oat.groupby(['persona','parameter','value']).agg(contexts=('driver','count'),changed_choice=('changed_choice','mean')).reset_index().to_csv(out/'oat_summary.csv',index=False)
    print(f'Replay: {len(frame)} contexts; {len(sensitivity)} factorial and {len(oat)} other sensitivity evaluations',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/persona_cpt_20261027')
    parser.add_argument('--replay-only',action='store_true',help='May run against the checkpointed context file while simulations continue')
    args=parser.parse_args()
    (args.output/'analysis_source_sha256.txt').write_text(hashlib.sha256(Path(__file__).read_bytes()).hexdigest()+'\n')
    if not args.replay_only:print(dynamic(args.output).to_string(index=False),flush=True)
    replay(args.output)


if __name__=='__main__':main()
