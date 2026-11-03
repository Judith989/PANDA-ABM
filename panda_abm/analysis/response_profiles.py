"""Outcome-free decision probes and exploratory response-profile discovery.

Profiles are descriptions produced after generation. They never feed back into
the ABM. Success, search outcomes and information access are not fitting inputs.
"""
from dataclasses import replace
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.decomposition import PCA
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits
from panda_abm.behavior.decision.base import DecisionContext
from panda_abm.behavior.decision.deterministic import DeterministicUtilityModel
from panda_abm.behavior.decision.random_utility import RandomUtilityModel
from panda_abm.behavior.decision.cpt import CPTDecisionModel
from panda_abm.environment.parking_space import ParkingSpace

MODELS={'deterministic':DeterministicUtilityModel,'rum':RandomUtilityModel,'cpt':CPTDecisionModel}
# Each row: walk metres, approach seconds, exit metres, supplied availability, restriction.
MENUS={
 'door_exit':[(20,65,240,.95,''),(170,12,25,.95,''),(95,30,120,.95,'')],
 'availability':[(30,45,180,.55,''),(140,18,90,.98,''),(85,30,140,.80,'')],
 'approach':[(20,90,140,.98,''),(180,5,140,.98,''),(90,35,140,.98,'')],
 'eligibility':[(15,30,180,.95,'accessible'),(35,15,80,.95,'reserved'),(145,20,60,.95,'')],
}
TIMES=(0.,180.,420.)
FEATURES=[f'{menu}_{int(t)}_{action}' for menu in MENUS for t in TIMES for action in ['s0','s1','s2','continue']]

def final_action_probabilities(result,model,threshold):
    """Include M1 probability mass rejected AFTER sampling, without Monte Carlo noise."""
    p=np.zeros(4)
    if model=='deterministic':
        p[int(result.chosen_space_id[1:]) if result.chosen_action=='park' else 3]=1.
    elif model=='rum':
        for item in result.candidate_evaluations:
            mass=result.probabilities.get(item.space_id,0.)
            p[int(item.space_id[1:]) if item.utility>=threshold else 3]+=mass
        if not result.probabilities:p[3]=1.
    elif result.chosen_action=='continue':p[3]=1.
    else:
        for name,mass in result.probabilities.items():p[int(name[1:])]=mass
    assert np.isfinite(p).all() and (p>=0).all() and np.isclose(p.sum(),1)
    return p

def response_fingerprint(driver,model,variant='primary'):
    """Apply the unmodified implemented decision model to a fixed common battery.

    Primary keeps each driver's actual eligibility, permit and walking limit.
    Neutral removes restrictions/bonuses in the probe candidates and walking cap.
    Perturbed changes probe walking/approach scales only, not driver parameters.
    No target acquisition or realized parking outcome occurs in these probes.
    """
    a=driver.attributes;policy=MODELS[model]();values=[]
    for menu,rows in MENUS.items():
        candidates=[];approaches={};beliefs={}
        for j,(walk,approach,exit_distance,q,restriction) in enumerate(rows):
            if variant=='perturbed':walk*=1.1;approach*=.9
            if variant=='neutral':restriction=''
            candidates.append(ParkingSpace(f's{j}','probe',walk,0.,
                accessible=restriction=='accessible',reserved_type='reserved' if restriction=='reserved' else None,
                distance_to_exit_a_m=exit_distance,distance_to_exit_b_m=exit_distance))
            approaches[f's{j}']=approach
            beliefs[f's{j}']=q*np.exp(-.002*approach)
        for elapsed in TIMES:
            context=DecisionContext(a.driver_id,driver.behavioral_parameters,driver.reference_points,
                elapsed,(0.,0.),(0.,0.),vehicle_type=a.vehicle_type,
                accessibility_eligibility=a.accessibility_eligibility,permit_type=a.permit_type,
                familiarity=a.local_familiarity,rng_seed=0,preferred_exit_id='exit_a',
                max_walking_distance_m=None if variant=='neutral' else a.max_walking_distance_m,
                approach_times_s=approaches,availability_probabilities=beliefs,
                remaining_search_time_s=600.-elapsed,cpt_parameters=driver.cpt_parameters)
            result=policy.evaluate_candidates(context,candidates)
            values.extend(final_action_probabilities(result,model,driver.behavioral_parameters.acceptance_utility_threshold))
    return np.array(values)

def coordinates(train,other):
    """Hellinger embedding of action distributions, training-only PCA; no outcomes."""
    a=np.sqrt(train);b=np.sqrt(other);pca=PCA(svd_solver='full').fit(a)
    dimension=min(6,max(1,int(np.searchsorted(np.cumsum(pca.explained_variance_ratio_),.95)+1)))
    za=pca.transform(a)[:,:dimension];zb=pca.transform(b)[:,:dimension]
    return za,zb,pca,dimension

def fit_profiles(features,seeds,train_seeds,validation_seeds,bootstrap=20,n_init=5,max_components=6):
    assert not set(train_seeds)&set(validation_seeds)
    tr=np.isin(seeds,train_seeds);va=np.isin(seeds,validation_seeds)
    assert tr.sum()>80 and va.sum()>40 and np.all(tr|va)
    a,b,pca,dim=coordinates(features[tr],features[va])
    settings=dict(covariance_type='full',n_init=n_init,max_iter=500,tol=1e-5,reg_covar=.001)
    selection=[];fitted=[]
    with threadpool_limits(limits=1):
        for k in range(1,max_components+1):
            g=GaussianMixture(n_components=k,random_state=20261102,**settings).fit(a)
            selection.append(dict(components=k,bic=float(g.bic(a)) if g.converged_ else np.inf,converged=bool(g.converged_)))
            fitted.append(g)
        ix=int(np.argmin([s['bic'] for s in selection]));g=fitted[ix];k=g.n_components
        assert g.converged_ and fitted[0].converged_
        la=g.predict(a);lb=g.predict(b)
        rng=np.random.default_rng(20261102)
        delta=g.score_samples(b)-fitted[0].score_samples(b)
        unit=np.array([delta[seeds[va]==seed].mean() for seed in validation_seeds])
        sampled=unit[rng.integers(len(unit),size=(5000,len(unit)))].mean(axis=1)
        stability=[];boot_converged=[]
        for repeat in range(bootstrap):
            chosen=rng.choice(train_seeds,size=len(train_seeds),replace=True)
            indices=np.concatenate([np.flatnonzero(seeds==s) for s in chosen])
            aa,bb,_,_=coordinates(features[indices],features[va])
            # Fix selected component count but refit the PCA and mixture on whole seed resamples.
            boot=GaussianMixture(n_components=k,random_state=repeat+1000,**settings).fit(aa)
            pred=boot.predict(bb);boot_converged.append(bool(boot.converged_))
            scores=np.zeros((k,k))
            for c in range(k):
                for d in range(k):scores[c,d]=np.sum((lb==c)&(pred==d))/max(1,np.sum((lb==c)|(pred==d)))
            rr,cc=linear_sum_assignment(-scores);matched=np.zeros(k);matched[rr]=scores[rr,cc]
            stability.append(matched)
    train_mass=np.bincount(la,minlength=k)/tr.sum();val_mass=np.bincount(lb,minlength=k)/va.sum()
    jaccard=np.mean(stability,axis=0);posterior=g.predict_proba(b).max(axis=1)
    lo,hi=np.quantile(sampled,[.025,.975]);bic_gain=selection[0]['bic']-selection[ix]['bic']
    supported=bool(k>1 and bic_gain>10 and lo>0 and min(train_mass)>=.05 and min(val_mass)>=.05
        and min(jaccard)>=.75 and np.mean(posterior>=.8)>=.5 and all(boot_converged))
    # Numbers follow training continuation propensity, never success or walking outcomes.
    order=sorted(range(k),key=lambda c:features[tr][la==c,3::4].mean())
    mapping={old:i+1 for i,old in enumerate(order)}
    latent=pca.transform(np.sqrt(features))[:,:dim];raw=g.predict(latent)
    groups=np.array([mapping[c] for c in raw]);confidence=g.predict_proba(latent).max(axis=1)
    model=dict(pca=pca,dimension=dim,gmm=g,mapping=mapping)
    result=dict(components=k,supported=supported,pca_dimensions=dim,train_n=int(tr.sum()),validation_n=int(va.sum()),
        bic_improvement=float(bic_gain),logscore_improvement=float(unit.mean()),logscore_ci_low=float(lo),logscore_ci_high=float(hi),
        min_train_mass=float(min(train_mass)),min_validation_mass=float(min(val_mass)),
        min_bootstrap_jaccard=float(min(jaccard)),confident_validation_fraction=float(np.mean(posterior>=.8)),
        bootstrap_converged=int(sum(boot_converged)),bootstrap_repetitions=bootstrap,
        per_group_bootstrap_jaccard={str(mapping[c]):float(jaccard[c]) for c in range(k)},selected_at_upper_bound=k==max_components)
    return result,groups,confidence,selection,model

def predict_profiles(model,features):
    z=model['pca'].transform(np.sqrt(features))[:,:model['dimension']]
    return np.array([model['mapping'][i] for i in model['gmm'].predict(z)])
