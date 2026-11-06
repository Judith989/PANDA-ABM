"""Explicit, opt-in urban visit-duration and parking-policy scenarios."""
from dataclasses import replace
import numpy as np
import math
from panda_abm.behavior.references import lot_distance_references

VISIT_RANGES={'short':(15,60),'near_limit':(90,120),'long':(150,240)}

def apply_policy(facility,policy):
    if policy=='configured':return facility
    if policy=='street_2h' and not any(s.parking_kind=='on_street' for s in facility.spaces):
        raise ValueError('Street-limit comparison requires classified on-street spaces')
    spaces=tuple(replace(s,time_limit_minutes=None if policy=='unrestricted' else 120 if s.parking_kind=='on_street' else s.time_limit_minutes) for s in facility.spaces)
    return replace(facility,spaces=spaces)

def apply_visit_profile(population,facility,profile,seed):
    if profile=='baseline':return population
    rng=np.random.default_rng(np.random.SeedSequence([seed,87119]));drivers=[]
    for driver in population.drivers:
        kind=str(rng.choice(list(VISIT_RANGES))) if profile=='mixed' else profile
        low,high=VISIT_RANGES[kind]
        attrs=replace(driver.attributes,expected_dwell_duration_s=int(rng.integers(low*60,high*60+1)))
        drivers.append(replace(driver,attributes=attrs,reference_points=lot_distance_references(facility,attrs,driver.reference_points)))
    return replace(population,drivers=tuple(drivers),parameterization=dict(population.parameterization or {},visit_profile=profile,visit_ranges_minutes=VISIT_RANGES,visit_assumption='uniform activity duration; mixed uses equal group probabilities; not calibrated'))


def urban_outcomes(model):
    rows=[];spaces=model.facility.space_by_id
    for a in model.agents:
        slot=spaces.get(a.chosen_space_id) if a.parking_time_s is not None else None
        walk=a.walking_distance_m if slot else None
        occupied_s=(getattr(a,'parking_released_s',model.clock_s)-a.parking_time_s) if slot else None
        rows.append(dict(observed_occupied_s=occupied_s,occupied_duration_censored=bool(slot and not hasattr(a,'parking_released_s')),observed_time_limit_exceeded=bool(slot and slot.time_limit_minutes is not None and occupied_s>slot.time_limit_minutes*60),pedestrian_wait_s=getattr(a,'pedestrian_wait_s',0.),walking_measure='pedestrian_network' if model.facility.pedestrian_network else 'euclidean',driver=a.driver_id,destination=a.attributes.walmart_door_id,activity_duration_s=a.attributes.expected_dwell_duration_s,
            parking_kind=slot.parking_kind if slot else None,time_limit_minutes=slot.time_limit_minutes if slot else None,
            expected_occupied_s=a.attributes.expected_dwell_duration_s+2*walk/model.walk_speed_m_per_s if slot else None,
            planned_stay_within_limit=slot.permits_planned_stay(a.attributes,model.walk_speed_m_per_s,walk) if slot else None))
    return rows


class ResidualBackground:
    """Assumed remaining stays of initially parked vehicles, not observed departures."""
    def __init__(self,model,profile,seed):
        import heapq
        self.model=model;self.heap=[];rng=np.random.default_rng(np.random.SeedSequence([seed,31197]))
        for sid,state in sorted(model.space_states.items()):
            if state.occupant_id!='initial_occupancy':continue
            kind=str(rng.choice(list(VISIT_RANGES))) if profile=='mixed' else 'short' if profile=='baseline' else profile
            low,high=VISIT_RANGES[kind];stay=float(rng.uniform(low*60,high*60));limit=model.facility.space_by_id[sid].time_limit_minutes
            if limit is not None:stay=min(stay,limit*60)
            remaining=max(1,int(math.ceil(stay*float(rng.random()))))
            heapq.heappush(self.heap,(remaining,sid))
    def step(self):
        import heapq
        from panda_abm.core.interventions import apply_intervention
        while self.heap and self.heap[0][0]<=self.model.clock_s:
            _,sid=heapq.heappop(self.heap)
            if self.model.resource_manager.occupant(sid)=='initial_occupancy':apply_intervention(self.model,dict(action='release',space_ids=[sid]))
