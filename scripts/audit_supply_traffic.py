"""Reproduce supply/traffic smoke experiments without changing publication data."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from panda_abm.twin.replay import build_replay_model, record_run
    from panda_abm.core.interventions import supply_snapshot
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/supply_traffic_20261104')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    records=[]
    for model_name in ('deterministic','rum','cpt'):
        for free in (0,5):
            settings=dict(model=model_name,information='space',initial_free_count=free,
                          population_size=32,arrival_interval_s=1,traffic_enabled=True,seed=1000)
            _,_,_,model=build_replay_model(settings)
            initial=supply_snapshot(model);start=time.perf_counter()
            model.run_until_complete()
            agents=list(model.agents)
            row=dict(settings=settings,initial=initial,final=supply_snapshot(model),
                     parked=sum(a.parking_time_s is not None for a in agents),
                     abandoned=sum(a.state.value=='abandoned' for a in agents),
                     max_search_s=max(a.search_time_s for a in agents),
                     duration_s=model.clock_s,wall_s=time.perf_counter()-start,
                     traffic=model.traffic.snapshot())
            assert initial['free']==free
            assert row['parked']+row['abandoned']==32
            assert row['max_search_s']<=600
            if free==0:assert row['parked']==0
            records.append(row)
            print(json.dumps({k:row[k] for k in ('parked','abandoned','duration_s','wall_s')}|dict(model=model_name,free=free)),flush=True)
    # Defaults must preserve an archived 80-driver reference, despite new options.
    replay=record_run(dict(population_size=80,seed=1000,occupancy=.8,model='cpt',information='space'),verify_archive=True)
    report=dict(status='passed',experiments=records,legacy_verification=replay['verification'],
                source_sha256=replay['source_sha256'],
                scope='Mechanism and reproducibility checks; not empirical traffic validation')
    (args.output/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Saved '+str(args.output/'audit.json'),flush=True)


if __name__=='__main__':main()
