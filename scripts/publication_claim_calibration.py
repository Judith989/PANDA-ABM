"""Compare assumed claim-survival beliefs with simulated claim outcomes.

This is an internal belief-consistency diagnostic; simulator outcomes are not
field calibration data. Cancelled/deadline targets are reported separately.
"""
from pathlib import Path
import json
import sys
import argparse
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.continuous import make_population
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.core.model import ParkingModel


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/publication_audit_20261027')
    out=parser.parse_args().output;out.mkdir(parents=True,exist_ok=True)
    if (out/'belief_design.json').exists():raise FileExistsError('Preserve frozen belief design')
    (out/'belief_design.json').write_text(json.dumps(dict(seeds=list(range(201,206)),occupancy=.95,
        drivers=80,models=['deterministic','rum','cpt'],hazard=.002,
        endpoint='Claim success among attempted targets; unresolved targets counted separately',
        interpretation='Internal consistency, not calibration to real drivers'),indent=2))
    facility=load_facility_from_lot_config(ROOT/'data/lot_config.json');rows=[];targeted=[]
    for seed in range(201,206):
        pop=make_population(facility,size=80,seed=seed)
        for name in ('deterministic','rum','cpt'):
            model=ParkingModel(facility,pop,name,seed=seed,run_id=f'belief_{seed}',decision_seed_namespace='matched',initial_occupancy_rate=.95)
            model.run_until_complete();pending={};evaluated={}
            for e in model.event_logger.records:
                if e.event_type=='CandidateEvaluated':
                    evaluated[e.agent_id,e.space_id]=e.details['feature_availability_probability']
                elif e.event_type=='TargetSelected':
                    pending[e.agent_id]=dict(seed=seed,model=name,driver=e.agent_id,space=e.space_id,
                        probability=evaluated[e.agent_id,e.space_id],selected_s=e.time_s)
                elif e.event_type in ('SpaceClaimSucceeded','SpaceClaimFailed'):
                    row=pending.pop(e.agent_id)
                    rows.append(dict(**row,success=e.event_type=='SpaceClaimSucceeded',claim_s=e.time_s))
            targeted.append(dict(seed=seed,model=name,attempted=sum(r['seed']==seed and r['model']==name for r in rows),unresolved=len(pending)))
            print(f'{seed} {name}',flush=True)
    pd.DataFrame(rows).to_csv(out/'claim_beliefs.csv',index=False)
    pd.DataFrame(targeted).to_csv(out/'claim_target_accounting.csv',index=False)
