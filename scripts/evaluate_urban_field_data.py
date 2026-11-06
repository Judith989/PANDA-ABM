"""Compare matched field observations with model outputs; no calibration is fitted."""
from pathlib import Path
import argparse,csv,json,math

def evaluate(observed,simulated):
    key=lambda r:(r['location_id'],float(r['time_s']))
    obs=list(csv.DictReader(Path(observed).open(encoding='utf-8-sig')));pred=list(csv.DictReader(Path(simulated).open(encoding='utf-8-sig')))
    if len({key(r) for r in obs})!=len(obs) or len({key(r) for r in pred})!=len(pred):raise ValueError('Duplicate location/time observations')
    pred={key(r):r for r in pred};rows=[r for r in obs if r.get('split','validation')=='validation']
    result={'scope':'Held-out field comparison; no fitting or fabricated observations','validation_rows':len(rows),'unmatched_rows':sum(key(r) not in pred for r in rows),'metrics':{}}
    for metric in ('queue_vehicles','speed_m_s','delay_s','occupancy_count'):
        pairs=[]
        for row in rows:
            if key(row) not in pred or not row.get(metric) or not pred[key(row)].get(metric):continue
            values=[float(row[metric]),float(pred[key(row)][metric])]
            if not all(math.isfinite(v) and v>=0 for v in values):raise ValueError('Measurements must be finite and nonnegative')
            pairs.append(values)
        if pairs:
            errors=[p-o for o,p in pairs];n=len(errors)
            result['metrics'][metric]=dict(n=n,mean_error=sum(errors)/n,mae=sum(abs(e) for e in errors)/n,rmse=math.sqrt(sum(e*e for e in errors)/n))
    if not result['metrics']:raise ValueError('No matched held-out measurements; supply actual observations first')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--observed',required=True);p.add_argument('--simulated',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    Path(a.output).write_text(json.dumps(evaluate(a.observed,a.simulated),indent=2)+'\n',encoding='utf8')
