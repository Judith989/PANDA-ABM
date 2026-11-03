"""Post-simulation behavioral density exploration, never an agent input.

Requires optional analysis dependencies. Components summarize search/walking
regimes; even a stable mixture is not automatically evidence of driver types.
"""
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits


def behavioral_features(frame):
    values=frame[['search_s','walk_relative']].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<0).any():raise ValueError('Behavioral features must be finite and nonnegative')
    return np.log1p(values)


def robust_coordinates(train,other):
    center=np.median(train,axis=0)
    scale=np.maximum(np.quantile(train,.75,axis=0)-np.quantile(train,.25,axis=0),.001)
    return (train-center)/scale,(other-center)/scale


def explore_behavioral_regimes(frame,train_seeds,validation_seeds,max_components=6,
                               n_init=10,bootstrap_repetitions=20,min_train=80,min_validation=40):
    """Fit on training seeds; evaluate fixed validation drivers and seed refits.

    BIC permits k=1. Operational screening gates are exploratory; homogeneous
    nulls and cross-context consistency must be assessed separately by callers.
    No parameter coefficients or persona names enter the clustering features.
    """
    if set(train_seeds)&set(validation_seeds):
        raise ValueError('Training and validation seeds must be disjoint')
    if bootstrap_repetitions<1 or n_init<1 or max_components<1:
        raise ValueError('Fit and bootstrap counts must be positive')
    train=frame[frame.seed.isin(train_seeds)].copy()
    validation=frame[frame.seed.isin(validation_seeds)].copy()
    result=dict(train_n=len(train),validation_n=len(validation),selected_components=1,
        candidate_supported=False,status='insufficient_sample')
    if len(train)<min_train or len(validation)<min_validation:return result,pd.DataFrame(),pd.DataFrame()
    a=behavioral_features(train);b=behavioral_features(validation)
    za,zb=robust_coordinates(a,b)
    settings=dict(covariance_type='full',n_init=n_init,max_iter=500,reg_covar=.001,tol=.00001)
    models=[];selection=[]
    with threadpool_limits(limits=1):
        for k in range(1,min(max_components,len(train)//10)+1):
            model=GaussianMixture(n_components=k,random_state=20261027,**settings).fit(za)
            bic=model.bic(za) if model.converged_ else float('inf')
            models.append(model);selection.append(dict(components=k,bic=bic,converged=bool(model.converged_)))
        chosen=int(np.argmin([r['bic'] for r in selection]));model=models[chosen];one=models[0]
        labels_train=model.predict(za);labels_validation=model.predict(zb)
        k=model.n_components
        train_mass=np.bincount(labels_train,minlength=k)/len(train)
        validation_mass=np.bincount(labels_validation,minlength=k)/len(validation)
        posterior=model.predict_proba(zb).max(axis=1)
        log_delta=model.score_samples(zb)-one.score_samples(zb)
        seed_scores=pd.DataFrame({'seed':validation.seed.to_numpy(),'delta':log_delta}).groupby('seed').delta.mean().to_numpy()
        rng=np.random.default_rng(20261027)
        bootstrap_scores=seed_scores[rng.integers(len(seed_scores),size=(5000,len(seed_scores)))].mean(axis=1)
        lower,upper=np.quantile(bootstrap_scores,[.025,.975])
        jaccards=[]
        if k>1:
            available=np.array(sorted(train.seed.unique()))
            for replicate in range(bootstrap_repetitions):
                sampled=rng.choice(available,size=len(available),replace=True)
                resample=pd.concat([train[train.seed==seed] for seed in sampled],ignore_index=True)
                ba,bb=robust_coordinates(behavioral_features(resample),b)
                boot=GaussianMixture(n_components=k,random_state=replicate+1000,**settings).fit(ba)
                prediction=boot.predict(bb)
                jaccards.append([max(np.sum((labels_validation==c)&(prediction==d))/max(1,np.sum((labels_validation==c)|(prediction==d))) for d in range(k)) for c in range(k)])
        stability=np.mean(jaccards,axis=0) if jaccards else np.ones(k)
    improvement=selection[0]['bic']-selection[chosen]['bic']
    supported=bool(k>1 and improvement>10 and lower>0 and min(train_mass)>=.05 and min(validation_mass)>=.05
        and min(stability)>=.75 and np.mean(posterior>=.8)>=.5)
    result.update(status='evaluated',selected_components=k,bic_improvement=improvement,
        heldout_log_score_improvement=float(np.mean(seed_scores)),heldout_log_score_ci_low=float(lower),heldout_log_score_ci_high=float(upper),
        min_train_mass=float(min(train_mass)),min_validation_mass=float(min(validation_mass)),
        confident_validation_fraction=float(np.mean(posterior>=.8)),min_bootstrap_jaccard=float(min(stability)),
        candidate_supported=supported,bootstrap_repetitions=bootstrap_repetitions)
    # Component numbers are made readable by ordering their training search
    # means, not by matching them to a desired persona vocabulary.
    order=sorted(range(k),key=lambda c:float(train.iloc[np.flatnonzero(labels_train==c)].search_s.mean()))
    mapping={old:new for new,old in enumerate(order)}
    pieces=[]
    for data,labels,is_validation,z in [(train,labels_train,False,za),(validation,labels_validation,True,zb)]:
        part=data.copy();part['behavior_regime']=[mapping[int(label)] for label in labels]
        part['validation']=is_validation;part['posterior']=model.predict_proba(z).max(axis=1)
        part['seed_bootstrap_jaccard']=[float(stability[int(label)]) for label in labels]
        pieces.append(part)
    assignments=pd.concat(pieces,ignore_index=True)
    for row in selection:row['selected']=row['components']==k
    return result,assignments,pd.DataFrame(selection)
