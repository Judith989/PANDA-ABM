"""Separate physical-resolution sensitivity from output-cadence invariance."""
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.environment import load_facility_from_lot_config
from panda_abm.core.model import ParkingModel


def main():
    out=ROOT/'results'/'search_timing_cpt_20261027'/'physical_resolution';out.mkdir(parents=True,exist_ok=True)
    facility=load_facility_from_lot_config(ROOT/'data'/'lot_config.json')
    pop=make_population(facility,size=80,seed=42,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
    rows=[]
    for resolution in (.5,.25):
        started=time.perf_counter()
        model=ParkingModel(facility,pop,decision_model='deterministic',seed=42,initial_occupancy_rate=.95,integration_seconds=resolution)
        model.run_until_complete();agents=list(model.agents);parked=[a for a in agents if a.parking_time_s is not None]
        rows.append(dict(seed=42,resolution=resolution,drivers=80,parked=len(parked),
            mean_search_all_s=sum(a.search_time_s for a in agents)/80,
            mean_search_parked_s=sum(a.search_time_s for a in parked)/len(parked),
            mean_walk_parked_m=sum(a.walking_distance_m for a in parked)/len(parked),seconds=time.perf_counter()-started))
        pd.DataFrame(rows).to_csv(out/'summary.csv',index=False)
        print(rows[-1],flush=True)


if __name__=='__main__':main()
