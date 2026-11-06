"""Native fixtures for the local engine/traffic-check.html browser check."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    from panda_abm.twin.platform import simulate
    from panda_abm.twin.replay import build_replay_model
    settings=dict(seed=1000,population_size=8,arrival_interval_s=1,traffic_enabled=True,information='space')
    cases=[settings|dict(model='deterministic',initial_free_count=0),
           settings|dict(model='rum',initial_free_count=5),
           settings|dict(model='cpt',initial_free_count=5)]
    _,facility,_,_=build_replay_model(settings)
    sid=next(s.space_id for s in facility.spaces if not s.unavailable and not s.accessible and not s.reserved_type)
    cases.append(settings|dict(model='cpt',initial_free_count=0,interventions=[dict(time_s=120,action='release',space_ids=[sid])]))
    records=[]
    for config in cases:
        result=simulate(config)
        records.append(dict(settings=config,outcomes=result['outcomes'],metrics=result['metrics'],traffic=result['traffic']))
        print(json.dumps(dict(model=config['model'],free=config['initial_free_count'],success_pct=result['metrics']['success_pct'])),flush=True)
    report=dict(cases=records,source_sha256={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'panda_abm').rglob('*.py'))})
    (ROOT/'dashboard/engine/traffic-fixtures.json').write_text(json.dumps(report,separators=(',',':')),encoding='utf-8')


if __name__=='__main__':main()
