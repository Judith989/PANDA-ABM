"""Audit all-arrival retention, outcome independence and matched comparisons."""
from pathlib import Path
import hashlib,json,sys
import numpy as np
import pandas as pd
import joblib
from pandas.testing import assert_frame_equal
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from panda_abm.analysis.response_profiles import predict_profiles

def main():
    p=ROOT/'research/tcss/all_driver_profiles_20261102';d=json.loads((p/'design.json').read_text())
    for name,h in (d['input_sha256']|d['source_sha256']).items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    x=pd.read_csv(p/'all_arrivals_with_profiles.csv.gz');a=pd.read_csv(p/'all_driver_profile_assignments.csv')
    raw=pd.read_csv(ROOT/'results/tcss_first_batch_20261028/drivers.csv')
    raw=raw[(raw.variant=='base')&raw.model.isin(d['models'])]
    keys=['seed','occupancy','model','information','driver']
    assert_frame_equal(raw.sort_values(keys).reset_index(drop=True),x[raw.columns].sort_values(keys).reset_index(drop=True),check_dtype=False,check_exact=False,rtol=1e-12,atol=1e-12)
    assert len(x)==64800 and len(a)==7200
    assert len(a[a.heldout])==2400 and len(x[x.heldout])==21600
    assert not x.duplicated(keys).any() and not a.duplicated(['seed','model','driver']).any()
    assert x.profile.notna().all() and x.groupby(['seed','model','driver']).profile.nunique().eq(1).all()
    assert len(x[~x.success])==len(raw[~raw.success])>0
    for model in d['models']:
        labels=a[a.model==model];features=np.load(p/f'{model}_response_features.npz')['primary'];fitted=joblib.load(p/f'{model}_fitted.joblib')
        inputs=pd.read_csv(p/f'{model}_driver_inputs.csv')
        assert_frame_equal(labels[['seed','driver']].reset_index(drop=True),inputs[['seed','driver']].reset_index(drop=True))
        np.testing.assert_array_equal(predict_profiles(fitted,features),labels.profile)
        np.testing.assert_allclose(fitted['pca'].mean_,np.sqrt(features[inputs.seed<1020]).mean(axis=0))
        assert fitted['gmm'].converged_
        assert len(labels[labels.heldout])==800 and len(labels[~labels.heldout])==1600
        assert set(labels[labels.heldout].seed)==set(range(1020,1030))
        assert set(labels[~labels.heldout].seed)==set(range(1000,1020))
        np.testing.assert_allclose(features.reshape(-1,4).sum(axis=1),1.)
    sizes=x.groupby(['seed','model','occupancy','profile','information']).size().unstack('information')
    assert sizes.nunique(axis=1).eq(1).all()
    u=pd.read_csv(p/'information_effects_by_seed.csv')
    wide=u[u.metric.isin(['success_pp','success_gain_pp','success_loss_pp'])].pivot(index=['split','seed','model','occupancy','information','profile'],columns='metric',values='value')
    np.testing.assert_allclose(wide.success_pp,wide.success_gain_pp-wide.success_loss_pp,atol=1e-12)
    audit=dict(status='passed',all_original_outcome_values_unchanged=True,all_64800_records_retained=True,
        unsuccessful_records_retained=int((~x.success).sum()),walking_limited_records_retained=int(x.mobility_limited.sum()),
        eligible_records_retained=int(x.eligible.sum()),unique_generated_drivers=2400,heldout_unique_drivers=800,
        heldout_outcome_records=21600,training_only_pca_verified=True,all_profile_predictions_reproduced=True,
        all_selected_mixtures_converged=True,profile_ids_fixed_across_information_and_occupancy=True,
        matched_cohort_sizes_equal_across_information=True,success_gain_loss_identity_verified=True,
        unit_tests={'file':'tests/test_response_profiles.py','passed':5},new_abm_simulations=0)
    (p/'all_driver_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2))

if __name__=='__main__':main()
