"""Replay a browser-exported comparison natively and check every driver."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from panda_abm.twin.platform import compare


def main():
    folder=ROOT/'paper/platform_evaluation'
    browser=json.loads((folder/'browser_comparison.json').read_text())
    native=compare({k:browser[k] for k in ('settings','models','replications')})
    errors=[];checked=0
    for a,b in zip(browser['runs'],native['runs']):
        assert a['settings']==b['settings']
        assert a['population_sha256']==b['population_sha256']
        assert a['initial_occupancy_sha256']==b['initial_occupancy_sha256']
        for x,y in zip(a['outcomes'],b['outcomes']):
            checked+=1
            for key in x:
                if isinstance(x[key],(float,int)) and not isinstance(x[key],bool) and isinstance(y[key],(float,int)):
                    if abs(x[key]-y[key])>1e-8:errors.append([x['driver'],key,x[key],y[key]])
                elif x[key]!=y[key]:errors.append([x['driver'],key,x[key],y[key]])
    for a,b in zip(browser['effects'],native['effects']):
        for key in a['metrics']:
            for field in ('mean','low','high','replications'):
                x,y=a['metrics'][key][field],b['metrics'][key][field]
                if x is None or y is None:
                    if x!=y:errors.append([key,field,x,y])
                elif abs(x-y)>1e-8:errors.append([key,field,x,y])
    report=dict(passed=not errors,scenarios=len(native['runs']),driver_scenario_records=checked,
        population_and_occupancy_hashes_exact=True,absolute_tolerance=1e-8,errors=errors,
        browser_runtime=browser['runtime'],native_runtime=native['runtime'])
    (folder/'matched_comparison_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report));assert not errors


if __name__=='__main__':main()
