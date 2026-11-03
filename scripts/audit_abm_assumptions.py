"""Conceptual diagnostics: time discretization, elapsed-time metrics, simple policies,
and scheduler tie-breaking. Does not modify production decision-model behavior.
"""
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.population import DriverAttributes,DriverSpec,PopulationSpec
from panda_abm.behavior.parameters import BehavioralParameters,PERSONA_PARAMETER_PROFILES
from panda_abm.behavior.references import ReferencePoints
from panda_abm.behavior.decision import DecisionResult,DeterministicUtilityModel
from panda_abm.core.model import ParkingModel
from panda_abm.environment import Facility,ParkingSpace,load_facility_from_lot_config


class SimplePolicy:
    def __init__(self,mode):self.model_name=mode
    def evaluate_candidates(self,context,candidates,**kwargs):
        base=DeterministicUtilityModel().evaluate_candidates(context,candidates)
        feasible=[e for e in base.candidate_evaluations if e.feasible]
        if not feasible:return DecisionResult('continue',None,None,base.candidate_evaluations)
        i=int(np.random.default_rng(context.rng_seed).integers(len(feasible))) if self.model_name=='uniform_feasible' else 0
        chosen=feasible[i]
        return DecisionResult('park',chosen.space_id,chosen.utility,base.candidate_evaluations)


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results'/'abm_concept_audit_20261027')
    args=parser.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    facility=load_facility_from_lot_config(ROOT/'data'/'lot_config.json')
    rows=[];drivers=[]
    for seed in (42,43,44):
        population=make_population(facility,size=80,seed=seed,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
        for policy,step in [('deterministic',5),('deterministic',10),('deterministic',20),('deterministic',30),
                            ('uniform_feasible',10),('first_feasible',10)]:
            model=ParkingModel(facility,population,decision_model=policy if policy=='deterministic' else SimplePolicy(policy),
                seed=seed,run_id=f'concept_{policy}_{step}_{seed}',step_seconds=step,initial_occupancy_rate=.95)
            model.run_until_complete()
            events=model.event_logger.records
            arrivals={r.agent_id:r.time_s for r in events if r.event_type=='AgentArrived'}
            search_starts={r.agent_id:r.time_s for r in events if r.event_type=='SearchStarted'}
            parks={r.agent_id:r.time_s for r in events if r.event_type=='ParkingStarted'}
            a=list(model.agents)
            for agent in a:
                drivers.append(dict(seed=seed,policy=policy,step_seconds=step,driver=agent.driver_id,
                    parked=agent.parking_time_s is not None,reported_search_s=agent.search_time_s,
                    arrival_to_park_s=parks[agent.driver_id]-arrivals[agent.driver_id] if agent.driver_id in parks else None,
                    search_start_to_park_s=parks[agent.driver_id]-search_starts[agent.driver_id] if agent.driver_id in parks else None))
            chosen=[x for x in a if x.parking_time_s is not None]
            row=dict(seed=seed,policy=policy,step_seconds=step,parked=len(chosen),drivers=len(a),
                mean_walk_parked_m=np.mean([x.walking_distance_m for x in chosen]),
                mean_reported_search_parked_s=np.mean([x.search_time_s for x in chosen]),
                mean_elapsed_arrival_to_park_s=np.mean([parks[x.driver_id]-arrivals[x.driver_id] for x in chosen]),
                mean_elapsed_search_to_park_s=np.mean([parks[x.driver_id]-search_starts[x.driver_id] for x in chosen]))
            rows.append(row);pd.DataFrame(rows).to_csv(out/'per_run.csv',index=False)
            print(row,flush=True)
    # Equal agents arriving at exactly the same instant to a single space.
    tiny=Facility('tie','Single-space tie',(ParkingSpace('only','A',0,0),),((0,0),),((0,0),),synthetic=True)
    pop=PopulationSpec('tie',42,tuple(DriverSpec(DriverAttributes(driver_id=n,destination_x_m=0,destination_y_m=0),BehavioralParameters(),ReferencePoints()) for n in ('A','B')))
    ties=[]
    for reverse in (False,True):
        model=ParkingModel(tiny,pop,decision_model='deterministic',initial_occupancy_rate=0)
        if reverse:model.agents.sort(key=lambda a:a.driver_id,ascending=False,inplace=True)
        model.run_until_complete()
        ties.append(dict(reverse=reverse,winners=[a.driver_id for a in model.agents if a.parking_time_s is not None]))
    (out/'ties.json').write_text(json.dumps(ties,indent=2)+'\n')
    pd.DataFrame(drivers).to_csv(out/'drivers.csv',index=False)
    summary=pd.DataFrame(rows).groupby(['policy','step_seconds']).mean(numeric_only=True).reset_index()
    summary.to_csv(out/'summary.csv',index=False)
    print(summary.to_string(index=False),flush=True);print(ties,flush=True)


if __name__=='__main__':main()
