"""Isolate CPT mathematics from its parking outcome adapter and response noise."""
from pathlib import Path
from dataclasses import replace
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pandas as pd
from scripts.audit_model_distinctness import Recorder
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES,parameters_for_persona
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.decision import CPTDecisionModel,DeterministicUtilityModel,RandomUtilityModel,DecisionContext
from panda_abm.behavior.decision.cpt import CPTParameters
from panda_abm.core.model import ParkingModel
from panda_abm.environment import load_facility_from_lot_config,ParkingSpace


def choice(result):return result.chosen_action,result.chosen_space_id


def main():
    out=ROOT/'results/model_distinctness_20261027';out.mkdir(parents=True,exist_ok=True)
    f=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    linear=CPTParameters(alpha=1,beta=1,lambda_loss=1,gamma=1,gamma_loss=1)
    rows=[]
    for scenario,occupancy in [('walmart_crowded',.8),('walmart_saturated',.95)]:
        for seed in [42,43,44]:
            pop=make_population(f,size=80,seed=seed,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
            personas={d.driver_id:d.attributes.persona for d in pop.drivers}
            recorder=Recorder()
            model=ParkingModel(f,pop,decision_model=recorder,seed=seed,initial_occupancy_rate=occupancy,
                run_id=f'{scenario}_deterministic_{seed}',scenario_id=scenario)
            model.run_until_complete()
            for index,(ctx,candidates) in enumerate(recorder.snapshots):
                if len(candidates)<2:continue
                ctx=replace(ctx,rng_seed=seed*100000+index,
                    behavioral_parameters=replace(ctx.behavioral_parameters,decision_temperature=0))
                full=CPTDecisionModel().evaluate_candidates(ctx,list(candidates))
                ev=CPTDecisionModel(linear).evaluate_candidates(ctx,list(candidates))
                m0=DeterministicUtilityModel().evaluate_candidates(ctx,list(candidates))
                certain=replace(ctx,availability_probabilities={s.space_id:1. for s in candidates})
                certain_full=CPTDecisionModel().evaluate_candidates(certain,list(candidates))
                certain_ev=CPTDecisionModel(linear).evaluate_candidates(certain,list(candidates))
                rows.append(dict(scenario=scenario,seed=seed,driver=ctx.driver_id,persona=personas[ctx.driver_id],
                    snapshot=index,candidates=len(candidates),cpt_vs_ev_same=choice(full)==choice(ev),
                    ev_vs_m0_same=choice(ev)==choice(m0),cpt_vs_m0_same=choice(full)==choice(m0),
                    certain_cpt_vs_ev_same=choice(certain_full)==choice(certain_ev)))
            pd.DataFrame(rows).to_csv(out/'mechanism_decisions.csv',index=False)
            print(f'mechanism control {scenario} seed {seed} complete',flush=True)
    pd.DataFrame(rows).groupby('persona').agg(decisions=('driver','count'),
        cpt_vs_ev_same=('cpt_vs_ev_same','mean'),ev_vs_m0_same=('ev_vs_m0_same','mean'),
        cpt_vs_m0_same=('cpt_vs_m0_same','mean'),certain_cpt_vs_ev_same=('certain_cpt_vs_ev_same','mean')).reset_index().to_csv(out/'mechanisms_by_persona.csv',index=False)
    probes=[]
    definitions=[
        ('door_vs_approach',[ParkingSpace('short_walk','A',20,0),ParkingSpace('quick_approach','A',110,0)],{'short_walk':60.,'quick_approach':5.},{},False),
        ('price_vs_walk',[ParkingSpace('near_paid','A',20,0,price_per_hour=9),ParkingSpace('far_free','A',110,0)],{}, {},False),
        ('rule_risk_vs_walk',[ParkingSpace('near_restricted','A',20,0,reserved_type='staff'),ParkingSpace('far_legal','A',110,0)],{},{},True),
        ('accessibility_vs_walk',[ParkingSpace('near_regular','A',20,0),ParkingSpace('far_accessible','A',70,0,accessible=True)],{},{},False),
        ('availability_vs_walk',[ParkingSpace('near_uncertain','A',20,0),ParkingSpace('far_likely','A',110,0)],{}, {'near_uncertain':.35,'far_likely':.95},False),
    ]
    for persona in PERSONA_PARAMETER_PROFILES:
        for probe,spaces,times,probabilities,illegal in definitions:
            params=replace(parameters_for_persona(persona),decision_temperature=0)
            ctx=DecisionContext('probe',params,ReferencePoints(r_walk_m=100,r_exit_m=150),0,(0,0),(0,0),
                accessibility_eligibility=persona=='accessibility_seeking',
                max_walking_distance_m=120. if persona=='accessibility_seeking' else None,
                allow_illegal_alternatives=illegal,rng_seed=42,approach_times_s=times,availability_probabilities=probabilities)
            for name,model in [('deterministic',DeterministicUtilityModel()),('rum',RandomUtilityModel()),('cpt',CPTDecisionModel())]:
                result=model.evaluate_candidates(ctx,spaces)
                probes.append(dict(persona=persona,probe=probe,model=name,action=result.chosen_action,
                    choice=result.chosen_space_id or 'continue',reason=result.diagnostics.get('reason','accepted')))
    pd.DataFrame(probes).to_csv(out/'controlled_persona_probes.csv',index=False)


if __name__=='__main__':main()
