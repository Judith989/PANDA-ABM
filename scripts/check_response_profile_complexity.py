"""Secondary training-only component-count diagnostic; never changes primary profiles."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from panda_abm.analysis.response_profiles import coordinates

def main():
    p=ROOT/'research/tcss/all_driver_profiles_20261102'
    plan=dict(status='frozen_before_secondary_fitting',purpose='Check the primary six-component upper bound and fit complexity on constraint-neutral probes. No outcome-based selection or replacement of primary assignments.',
        k=list(range(1,11)),n_init=5,train_seeds=list(range(1000,1020)),outcome_variables_used=False)
    (p/'complexity_sensitivity_design.json').write_text(json.dumps(plan,indent=2)+'\n')
    rows=[]
    with threadpool_limits(limits=1):
        for model in ['deterministic','rum','cpt']:
            frame=pd.read_csv(p/f'{model}_driver_inputs.csv');data=np.load(p/f'{model}_response_features.npz');tr=frame.seed<1020
            for variant in ['primary','neutral']:
                a,_,_,dim=coordinates(data[variant][tr],data[variant][~tr])
                for k in range(1,11):
                    g=GaussianMixture(n_components=k,covariance_type='full',n_init=5,max_iter=500,tol=1e-5,reg_covar=.001,random_state=20261102).fit(a)
                    rows.append(dict(model=model,variant=variant,components=k,pca_dimensions=dim,bic=g.bic(a),converged=bool(g.converged_)))
                print(model,variant,'training-only best K',min(rows[-10:],key=lambda r:r['bic'])['components'],flush=True)
    pd.DataFrame(rows).to_csv(p/'complexity_sensitivity.csv',index=False)
    plan['status']='completed';(p/'complexity_sensitivity_design.json').write_text(json.dumps(plan,indent=2)+'\n')

if __name__=='__main__':main()
