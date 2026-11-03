"""Generic driver generation from explicit continuous structural priors.

These distributions are experimental assumptions, not fitted parking estimates.
Attribute, preference, reference and CPT RNG streams are separate so matched
homogeneous controls retain exactly the same trips and physical constraints.
"""
from dataclasses import asdict,dataclass
import json
import math
import numpy as np
from panda_abm.behavior.parameters import BehavioralParameters
from panda_abm.behavior.population import DriverAttributes,DriverSpec,PopulationSpec
from panda_abm.behavior.references import ReferencePoints,lot_distance_references
from panda_abm.behavior.cpt_parameters import CPTParameters

# Positive coefficient means sum to 3.2: one continuous preference simplex,
# rather than a mixture centered on named archetypes. Inactive features remain
# fixed instead of manufacturing heterogeneity in unused parameters.
PREFERENCE_MEANS={
    'beta_walk':.65,'beta_price':.4,'beta_search':.45,
    'beta_availability':.65,'beta_risk':.35,'beta_familiarity':.2,
    'beta_exit':.15,'beta_approach':.2,'beta_accessibility':.15,
}


@dataclass(frozen=True)
class PopulationPriors:
    """Source-tagged assumptions; concentration controls dispersion, not classes."""
    preference_concentration: float = 32.
    temperature_median: float = .35
    temperature_log_sd: float = .25
    search_reference_median_s: float = 300.
    search_reference_log_sd: float = .25
    cpt_lambda_median: float = 2.25
    cpt_lambda_log_sd: float = .25
    cpt_value_mean: float = .88
    cpt_value_precision: float = 40.
    cpt_weight_gain_mean: float = .61
    cpt_weight_loss_mean: float = .69
    cpt_weight_precision: float = 25.
    accessibility_probability: float = .08
    mobility_limitation_probability: float = .10
    reserved_permit_probability: float = .03
    walking_limit_min_m: float = 50.
    walking_limit_max_m: float = 150.
    arrival_interval_s: float = 20.
    source: str = 'structural_continuous_prior_v1_not_calibrated'

    def __post_init__(self):
        for key,value in asdict(self).items():
            if key!='source' and not math.isfinite(value):raise ValueError(f'Nonfinite prior: {key}')
        for key in ('preference_concentration','temperature_median','search_reference_median_s','cpt_lambda_median','cpt_value_precision','cpt_weight_precision'):
            if getattr(self,key)<=0:raise ValueError(f'Nonpositive prior: {key}')
        for key in ('temperature_log_sd','search_reference_log_sd','cpt_lambda_log_sd','arrival_interval_s'):
            if getattr(self,key)<0:raise ValueError(f'Negative prior: {key}')
        for key in ('accessibility_probability','mobility_limitation_probability','reserved_permit_probability'):
            if not 0<=getattr(self,key)<=1:raise ValueError(f'Invalid probability: {key}')
        if not 0<self.cpt_value_mean<1:raise ValueError('CPT value mean must lie in (0,1)')
        if not .28<self.cpt_weight_gain_mean<1 or not .28<self.cpt_weight_loss_mean<1:raise ValueError('CPT weighting means must lie in (.28,1)')
        if not 0<self.walking_limit_min_m<=self.walking_limit_max_m:raise ValueError('Invalid walking limits')


def sample_preferences(rng,priors,heterogeneous=True):
    means=np.array(list(PREFERENCE_MEANS.values()))
    weights=rng.dirichlet(priors.preference_concentration*means/means.sum())*means.sum() if heterogeneous else means
    return BehavioralParameters(**dict(zip(PREFERENCE_MEANS,weights)),
        decision_temperature=float(rng.lognormal(np.log(priors.temperature_median),priors.temperature_log_sd)) if heterogeneous else priors.temperature_median)


def sample_cpt(rng,priors,heterogeneous=True):
    if not heterogeneous:return CPTParameters(alpha=priors.cpt_value_mean,beta=priors.cpt_value_mean,
        lambda_loss=priors.cpt_lambda_median,gamma=priors.cpt_weight_gain_mean,gamma_loss=priors.cpt_weight_loss_mean)
    def value():return float(rng.beta(priors.cpt_value_mean*priors.cpt_value_precision,(1-priors.cpt_value_mean)*priors.cpt_value_precision))
    def weight(mean):
        fraction=(mean-.28)/.72
        return float(.28+.72*rng.beta(fraction*priors.cpt_weight_precision,(1-fraction)*priors.cpt_weight_precision))
    return CPTParameters(alpha=value(),beta=value(),lambda_loss=float(rng.lognormal(np.log(priors.cpt_lambda_median),priors.cpt_lambda_log_sd)),
        gamma=weight(priors.cpt_weight_gain_mean),gamma_loss=weight(priors.cpt_weight_loss_mean))


def make_population(facility,size=12,seed=42,heterogeneous=True,population_id=None,
                    priors=None,cpt_parameter_mode='continuous'):
    """Generate generic drivers. No persona argument, assignment or lookup.

    Constraints are attribute/scenario inputs. Familiarity, urgency and value of
    time remain observed/context attributes; no unvalidated mapping from those
    attributes to preference coefficients is silently imposed.
    """
    priors=priors or PopulationPriors()
    if size<0 or not isinstance(size,int):raise ValueError('Population size must be a nonnegative integer')
    if cpt_parameter_mode not in ('continuous','shared'):raise ValueError('CPT parameter mode must be continuous or shared')
    streams=[np.random.default_rng(np.random.SeedSequence([seed,key])) for key in (2201,2202,2203,2204)]
    attributes_rng,preferences_rng,references_rng,cpt_rng=streams
    module_points={}
    for s in facility.spaces:module_points.setdefault(s.module_id,[]).append((s.x_m,s.y_m))
    destinations=facility.walmart_doors or tuple(tuple(np.mean(points,axis=0)) for _,points in sorted(module_points.items()))
    if size and not destinations:raise ValueError('Cannot generate trips without a destination or facility spaces')
    drivers=[]
    for i in range(size):
        dest=destinations[int(attributes_rng.integers(len(destinations)))]
        entry=int(attributes_rng.integers(len(facility.entry_point_ids))) if facility.entry_point_ids else None
        arrival_id=facility.entry_point_ids[entry] if entry is not None else None
        exit_index=(facility.exit_point_ids.index(arrival_id) if arrival_id in facility.exit_point_ids
            else int(attributes_rng.integers(len(facility.exit_point_ids))) if facility.exit_point_ids else None)
        eligible=bool(attributes_rng.random()<priors.accessibility_probability)
        mobility=bool(attributes_rng.random()<priors.mobility_limitation_probability)
        # Permit ownership and physical mobility are distinct. The existing
        # scalar permit schema cannot express concurrent permit categories.
        reserved=bool(attributes_rng.random()<priors.reserved_permit_probability)
        walking_limit=float(attributes_rng.uniform(priors.walking_limit_min_m,priors.walking_limit_max_m)) if mobility else None
        door_index=destinations.index(dest)
        attrs=DriverAttributes(driver_id=f'D{i:04d}',destination_x_m=float(dest[0]),destination_y_m=float(dest[1]),
            persona=None,arrival_exit_id=facility.entry_point_ids[entry] if entry is not None else None,
            preferred_exit_id=facility.exit_point_ids[exit_index] if exit_index is not None else None,
            walmart_door_id=facility.walmart_door_ids[door_index] if facility.walmart_door_ids else None,
            trip_purpose='shopping',expected_dwell_duration_s=int(attributes_rng.integers(900,3600)),
            arrival_time_s=i*priors.arrival_interval_s,local_familiarity=float(attributes_rng.beta(3,2)),
            accessibility_eligibility=eligible,mobility_limitation=mobility,max_walking_distance_m=walking_limit,
            permit_type='accessible' if eligible else 'reserved' if reserved else None,
            vehicle_type=str(attributes_rng.choice(['sedan','compact','suv','van','truck'],p=[.42,.18,.24,.10,.06])),
            vehicle_occupancy=int(attributes_rng.integers(1,5)),trip_urgency=float(attributes_rng.beta(2,2)),
            value_of_time=float(attributes_rng.lognormal(0,.25)))
        preferences=sample_preferences(preferences_rng,priors,heterogeneous)
        search_reference=float(references_rng.lognormal(np.log(priors.search_reference_median_s),priors.search_reference_log_sd)) if heterogeneous else priors.search_reference_median_s
        references=lot_distance_references(facility,attrs,ReferencePoints(r_search_s=search_reference))
        cp=sample_cpt(cpt_rng,priors,heterogeneous) if cpt_parameter_mode=='continuous' else CPTParameters()
        drivers.append(DriverSpec(attrs,preferences,references,cp,
            priors.source if cpt_parameter_mode=='continuous' else 'shared_tk92_benchmark'))
    specification=dict(method='continuous_generic_v1',priors=asdict(priors),preference_means=PREFERENCE_MEANS,
        preference_weight_sum=3.2,cpt_parameter_mode=cpt_parameter_mode,heterogeneous=heterogeneous,
        note='No persona assignment; structural priors and physical attributes are not calibrated. No unsupported attribute-to-preference mapping.')
    return PopulationSpec(population_id or f'continuous_{size}_{seed}_{"het" if heterogeneous else "hom"}_{cpt_parameter_mode}',seed,tuple(drivers),
        generation_notes=json.dumps(specification,sort_keys=True),generation_method='continuous_generic_v1',parameterization=specification)
