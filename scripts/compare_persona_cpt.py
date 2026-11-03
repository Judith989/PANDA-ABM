"""Frozen, paired shared/persona CPT experiment with seed-level uncertainty.

Illustrative persona hypotheses are not fitted human preferences. The design
manifest and source archive are written before simulations; no result tuning.
"""
from pathlib import Path
from dataclasses import replace,asdict
import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from panda_abm.behavior.factory import make_controlled_population as make_population
from panda_abm.behavior.parameters import PERSONA_PARAMETER_PROFILES
from panda_abm.behavior.cpt_parameters import CPTParameters,PERSONA_CPT_PROFILES,PERSONA_CPT_PROFILE_VERSION
from panda_abm.behavior.decision import CPTDecisionModel
from panda_abm.core.model import ParkingModel
from panda_abm.core.states import DriverState
from panda_abm.environment import load_facility_from_lot_config,generate_synthetic_facility

SCENARIOS=[('walmart_crowded',.8,80),('walmart_saturated',.95,80),('synthetic_rule_tradeoff',.35,40)]


class RecordingCPT:
    model_name='cpt'
    def __init__(self):self.base=CPTDecisionModel();self.snapshots=[];self.counts={}
    def evaluate_candidates(self,context,candidates,*args,**kwargs):
        if candidates and self.counts.get(context.driver_id,0)<3:
            self.snapshots.append((context,tuple(candidates)))
            self.counts[context.driver_id]=self.counts.get(context.driver_id,0)+1
        return self.base.evaluate_candidates(context,candidates,*args,**kwargs)


def archive_design(out,seeds):
    files=sorted([*ROOT.glob('panda_abm/**/*.py'),*ROOT.glob('scripts/*.py'),*ROOT.glob('tests/*.py'),
                  *ROOT.glob('research/*.md'),ROOT/'data/lot_config.json',ROOT/'README.md'])
    hashes={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    design=dict(profile_version=PERSONA_CPT_PROFILE_VERSION,seeds=seeds,scenarios=SCENARIOS,
        benchmark=CPTParameters().as_dict(),persona_profiles={k:v.as_dict() for k,v in PERSONA_CPT_PROFILES.items()},
        hypothesis='Risk-averse lambda=3 versus shared 2.25; other persona CPT parameters unchanged. Researcher-selected, not fitted.',
        matched='identical driver attributes, utility parameters, references, initial occupancy, run IDs and RNG streams within arms',
        primary_endpoints=['per-persona seed-level success fraction','per-persona seed-level mean search including abandonment'],
        secondary_endpoints=['same final space among jointly parked','walking distance among jointly parked','claim belief among jointly parked','identical-context noise-free choice changes'],
        uncertainty='5000 seed-cluster paired bootstrap resamples; percentile 95% intervals; exploratory, no multiple-testing claims',
        replay='First three nonempty shared-CPT contexts per driver, common RNG, zero-temperature choice control.',
        sensitivity=dict(lambda_loss=[1,1.6,2.25,3,4],hazard_multiplier=[0,.5,1,2],door_reference_multiplier=[.75,1,1.25],
            subset='First two multi-feasible contexts per scenario/seed/persona; selected independently of outcomes',
            additional_oat='alpha/beta .7,.88,1; gamma/gamma_loss .5,.7,.9,1; temperature 0,.175,.35,.7; outcome scale .5,1,2'),
        simulation=dict(integration_seconds=1,decision_interval_s=10,claim_hazard_per_s=.002,max_search_time_s=600,
            initial_background_vehicles_depart=False),
        limitations=['No site/persona CPT calibration','Ten seeds are a pilot, not convergence or power proof','Composite utility, not attribute-specific loss aversion',
            'Static initial occupancy and inferred aisle graph','Continuation uses observed-offer persistence'],
        python=platform.python_version(),dependencies={name:importlib.metadata.version(name) for name in ['numpy','pandas','mesa']},source_sha256=hashes)
    design['git_commit']=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
    (out/'design.json').write_text(json.dumps(design,indent=2)+'\n',encoding='utf-8')
    with zipfile.ZipFile(out/'source_snapshot.zip','w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:archive.write(path,str(path.relative_to(ROOT)))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/persona_cpt_20261027')
    parser.add_argument('--seeds',type=int,nargs='+',default=list(range(42,52)))
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    if (out/'design.json').exists():raise FileExistsError('Choose a fresh output directory to preserve the frozen design')
    archive_design(out,args.seeds)
    walmart=load_facility_from_lot_config(ROOT/'data/lot_config.json')
    drivers=[];runs=[];checks=[]
    with (out/'replay_contexts.jsonl').open('w',encoding='utf-8') as snapshots:
        for scenario,occupancy,size in SCENARIOS:
            for seed in args.seeds:
                facility=walmart if scenario.startswith('walmart') else generate_synthetic_facility(seed)
                illegal=scenario=='synthetic_rule_tradeoff'
                if illegal:facility=replace(facility,spaces=tuple(replace(s,price_per_hour=0. if s.accessible or s.reserved_type else 9.) for s in facility.spaces))
                shared=make_population(facility,size=size,seed=seed,personas=tuple(PERSONA_PARAMETER_PROFILES),cpt_profile_mode='shared')
                persona=replace(shared,population_id=shared.population_id+'_persona',drivers=tuple(replace(d,
                    cpt_parameters=PERSONA_CPT_PROFILES[d.attributes.persona],cpt_parameter_source=PERSONA_CPT_PROFILE_VERSION) for d in shared.drivers))
                assert all((a.attributes,a.behavioral_parameters,a.reference_points)==(b.attributes,b.behavioral_parameters,b.reference_points) for a,b in zip(shared.drivers,persona.drivers))
                initial=None
                for arm,population in [('shared',shared),('persona',persona)]:
                    recorder=RecordingCPT()
                    model=ParkingModel(facility,population,decision_model=recorder,seed=seed,initial_occupancy_rate=occupancy,
                        run_id=f'{scenario}_cpt_{seed}',scenario_id=scenario,allow_illegal_alternatives=illegal)
                    occupied={sid for sid,s in model.space_states.items() if s.occupied}
                    if initial is None:initial=occupied
                    assert initial==occupied
                    model.run_until_complete()
                    active={};safe=True
                    for e in model.event_logger.records:
                        if e.event_type=='SpaceClaimSucceeded':
                            if e.space_id in active:safe=False
                            active[e.space_id]=e.agent_id
                        elif e.event_type=='SpaceReleased':active.pop(e.space_id,None)
                    finite=all(np.isfinite(e.utility) for e in model.event_logger.records if e.utility is not None)
                    terminal=all(a.state in (DriverState.LEFT,DriverState.ABANDONED) for a in model.agents)
                    elapsed=all(a.search_time_s==a.search_ended_s-a.search_started_s for a in model.agents)
                    legal=illegal or not any(a.violation for a in model.agents)
                    assert safe and finite and terminal and elapsed and legal
                    checks.append(dict(scenario=scenario,seed=seed,arm=arm,no_double_claims=safe,finite=finite,terminal=terminal,elapsed_identity=elapsed,legal_if_required=legal))
                    rows=[]
                    for a in model.agents:
                        success=a.parking_time_s is not None
                        space=facility.space_by_id.get(a.chosen_space_id) if success else None
                        rows.append(dict(scenario=scenario,seed=seed,arm=arm,driver=a.driver_id,persona=a.attributes.persona,
                            success=success,search_s=a.search_time_s,walk_m=a.walking_distance_m,
                            chosen_space=space.space_id if space else None,violation=a.violation,rejected=a.rejected_spaces,
                            claim_probability=a._candidate_probabilities.get(space.space_id) if space else None,
                            approach_s=a._candidate_times.get(space.space_id) if space else None,
                            lambda_loss=a.spec.cpt_parameters.lambda_loss,r_walk_m=a.reference_points.r_walk_m,
                            r_exit_m=a.reference_points.r_exit_m))
                    drivers.extend(rows)
                    runs.append(dict(scenario=scenario,seed=seed,arm=arm,drivers=size,parked=sum(r['success'] for r in rows),
                        mean_search_s=float(np.mean([r['search_s'] for r in rows]))))
                    pd.DataFrame(drivers).to_csv(out/'drivers.csv',index=False)
                    pd.DataFrame(runs).to_csv(out/'runs.csv',index=False)
                    (out/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
                    if arm=='shared':
                        personas={d.driver_id:d.attributes.persona for d in shared.drivers}
                        for index,(ctx,candidates) in enumerate(recorder.snapshots):
                            snapshot=dict(scenario=scenario,seed=seed,snapshot=index,persona=personas[ctx.driver_id],
                                context=asdict(ctx),candidates=[asdict(s) for s in candidates])
                            snapshots.write(json.dumps(snapshot,default=lambda value:value.value)+'\n')
                        snapshots.flush()
                    print(f'{scenario} seed {seed} {arm}: {runs[-1]["parked"]}/{size} parked',flush=True)


if __name__=='__main__':main()
