"""Trace CPT rejections without changing driver information or decision rules."""
from pathlib import Path
import argparse
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.behavior.decision.cpt import cumulative_prospect_value
from panda_abm.core.model import ParkingModel
from panda_abm.environment import load_facility_from_lot_config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    rows=[]
    for occupancy in (.8,.95):
        population=make_population(facility,size=80,seed=42,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
        specs={s.driver_id:s for s in population.drivers}
        scenario='walmart_crowded' if occupancy==.8 else 'walmart_saturated'
        model=ParkingModel(facility,population,decision_model='cpt',seed=42,initial_occupancy_rate=occupancy,
            run_id=f'{scenario}_cpt_42',scenario_id=scenario,replication_id='seed_42')
        model.run_until_complete()
        candidates={}
        for event in model.event_logger.records:
            key=(event.agent_id,event.time_s)
            if event.event_type=='CandidateEvaluated':
                candidates.setdefault(key,[]).append(event)
            elif event.event_type=='CandidateRejected':
                spec=specs[event.agent_id];threshold=spec.behavioral_parameters.acceptance_utility_threshold
                feasible=[e for e in candidates.pop(key,[]) if e.details['feasible']]
                absolute=[e for e in feasible if e.details['cpt_success_utility']>=threshold]
                acceptable=[e for e in absolute if e.utility>=e.details['cpt_continuation_value']]
                # Counterfactual for the old comparison's inconsistent time horizon.
                elapsed=event.search_time_s
                elapsed_cont=cumulative_prospect_value(((-spec.behavioral_parameters.beta_search*(elapsed+model.decision_interval_s)/600,1.),))
                rows.append(dict(occupancy=occupancy,driver=event.agent_id,persona=spec.attributes.persona,
                    search_time_s=elapsed,reason=event.details.get('reason'),candidates=len(feasible),
                    absolute_acceptable=len(absolute),gate_acceptable=len(acceptable),
                    within_door_reference=sum(e.details['feature_walking_distance_m']<=spec.reference_points.r_walk_m for e in absolute),
                    within_120m=sum(e.details['feature_walking_distance_m']<=120 for e in absolute),
                    acceptable_with_elapsed_continuation=sum(e.utility>=elapsed_cont for e in absolute)))
        print(f'occupancy {occupancy}: parked {sum(a.parking_time_s is not None for a in model.agents)}/80',flush=True)
    frame=pd.DataFrame(rows);frame.to_csv(args.output/'rejections.csv',index=False)
    summary=frame.groupby(['occupancy','reason']).agg(decisions=('driver','count'),
        with_absolute_acceptable=('absolute_acceptable',lambda s:int((s>0).sum())),
        with_gate_acceptable=('gate_acceptable',lambda s:int((s>0).sum())),
        with_reasonable_120m=('within_120m',lambda s:int((s>0).sum())),
        with_space_at_or_below_reference=('within_door_reference',lambda s:int((s>0).sum())),
        with_elapsed_comparison_acceptable=('acceptable_with_elapsed_continuation',lambda s:int((s>0).sum()))).reset_index()
    summary.to_csv(args.output/'summary.csv',index=False);print(summary.to_string(index=False))


if __name__=='__main__':main()
