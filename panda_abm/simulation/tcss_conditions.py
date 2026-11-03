"""Explicit experimental conditions; default settings retain the core model.

Current-information services do not reserve spaces or predict future occupancy.
"""
from collections import deque
from dataclasses import replace
import math
import numpy as np
from panda_abm.core.model import ParkingModel
from panda_abm.behavior.decision.base import DecisionResult
from panda_abm.behavior.decision.deterministic import DeterministicUtilityModel
from panda_abm.environment.information import AisleInformationService,AisleInformation
from panda_abm.environment.perception import RadiusPerception,SpaceInformationPerception,PerceivedSpace
from panda_abm.environment.facility import Facility


class SimpleSearchDecisionModel:
    """Accept nearest graph-reachable local feasible offer, else nearest report."""
    model_name='simple'

    def __init__(self,radius_m=60.):self.radius_m=radius_m

    def evaluate_candidates(self,context,candidates,perceived_state=None,forecast=None):
        result=DeterministicUtilityModel().evaluate_candidates(context,candidates,perceived_state,forecast)
        feasible=[e for e in result.candidate_evaluations if e.feasible]
        if not feasible:return DecisionResult('continue',None,None,result.candidate_evaluations)
        by_id={s.space_id:s for s in candidates}
        local=[e for e in feasible if math.dist(context.current_position_m,(by_id[e.space_id].x_m,by_id[e.space_id].y_m))<=self.radius_m+1e-9]
        chosen=min(local or feasible,key=lambda e:(e.features['approach_time_s'],e.space_id))
        return DecisionResult('park',chosen.space_id,chosen.utility,result.candidate_evaluations,
            {e.space_id:float(e.space_id==chosen.space_id) for e in feasible})


class ExperimentalAisleInformation(AisleInformationService):
    def snapshot(self,agent):
        if not self.model.report_delay_s:return super().snapshot(agent)
        timestamp,available=self.model.remote_snapshot()
        static=self._prepare(agent)
        return AisleInformation(timestamp,{a:sum(available[s] for s in ids) for a,(ids,_) in static.items()},
            {a:len(ids) for a,(ids,_) in static.items()})

    def plan_search(self,agent,report):
        if self.model.decision_model_name!='simple':return super().plan_search(agent,report)
        nav=self.model.navigation
        positive=sorted(a for a,n in report.free_counts.items() if n>0)
        if not positive:
            if agent.information_aisle_id is not None:agent.route=[];agent.patrol_goal=None
            agent.information_aisle_id=None
            return False
        if agent.information_aisle_id in positive and agent.route:return True
        distances=nav.distances((agent.x_m,agent.y_m),{n for a in positive for n in nav.aisle_nodes[a]})
        aisle=min(positive,key=lambda a:(min(distances[n] for n in nav.aisle_nodes[a]),a))
        entry,other=sorted(nav.aisle_nodes[aisle],key=lambda n:(distances[n],n))
        agent.route=nav.route((agent.x_m,agent.y_m),entry)+nav.route(nav.positions[entry],other)
        agent.patrol_goal=other;agent.information_aisle_id=aisle;agent.information_route_changes+=1
        agent.log('InformationSearchAreaSelected',details=dict(aisle_id=aisle,free_count=report.free_counts[aisle],
            compatible_capacity=report.compatible_capacity[aisle],report_time_s=report.observed_at_s,
            area_score=-distances[entry],entry_node=entry,end_node=other))
        return True


class ExperimentalParkingModel(ParkingModel):
    def __init__(self,*args,adoption_rate=1.,report_delay_s=0.,background_median_s=None,**kwargs):
        if not math.isfinite(adoption_rate) or not 0<=adoption_rate<=1:raise ValueError('Invalid adoption')
        if not math.isfinite(report_delay_s) or report_delay_s<0:raise ValueError('Invalid delay')
        if background_median_s is not None and (not math.isfinite(background_median_s) or background_median_s<=0):raise ValueError('Invalid background lifetime')
        self.adoption_rate=adoption_rate;self.report_delay_s=report_delay_s
        super().__init__(*args,**kwargs)
        rng=np.random.default_rng(np.random.SeedSequence([self.seed,80421]))
        self.adoption_draws={a.driver_id:float(rng.random()) for a in sorted(self.agents,key=lambda a:a.driver_id)}
        self.adopters={k for k,v in self.adoption_draws.items() if v<adoption_rate}
        self.aisle_information=ExperimentalAisleInformation(self)
        self._snapshots=deque([(0.,self.availability_snapshot())])
        rng=np.random.default_rng(np.random.SeedSequence([self.seed,80422]))
        initial=sorted(s for s,v in self.space_states.items() if v.occupant_id=='initial_occupancy')
        self.background_departures=deque(sorted((float(rng.exponential(background_median_s/math.log(2))),s)
            for s in initial)) if background_median_s is not None else deque()
        self.background_schedule=tuple(self.background_departures)

    def information_mode_for(self,agent):
        return self.information_mode if agent.driver_id in self.adopters else 'unaided'

    def availability_snapshot(self):
        return {s:not(v.occupied or v.unavailable) for s,v in self.space_states.items()}

    def before_physical_tick(self):
        while self.background_departures and self.background_departures[0][0]<=self.clock_s+1e-9:
            due,sid=self.background_departures.popleft()
            assert self.resource_manager.release_space('initial_occupancy',sid)
            self.event_logger.log('BackgroundSpaceReleased',self.clock_s,space_id=sid,details={'scheduled_s':due})
        if self.report_delay_s and self.clock_s>self._snapshots[-1][0]:
            self._snapshots.append((self.clock_s,self.availability_snapshot()))
            target=self.clock_s-self.report_delay_s
            while len(self._snapshots)>1 and self._snapshots[1][0]<=target+1e-9:self._snapshots.popleft()

    def remote_snapshot(self):return self._snapshots[0]

    def perceive(self,agent):
        mode=self.information_mode_for(agent)
        if mode!='space':return RadiusPerception(self.perception_radius_m).observe(self,agent)
        if not self.report_delay_s:return SpaceInformationPerception().observe(self,agent)
        timestamp,available=self.remote_snapshot();observations=[]
        for s in self.facility.spaces:
            distance=math.dist((s.x_m,s.y_m),(agent.x_m,agent.y_m))
            local=distance<=self.perception_radius_m
            free=self.resource_manager.is_available(s.space_id) if local else available[s.space_id]
            observations.append(PerceivedSpace(s,distance,not free,free,None,
                'local' if local else 'space_report',self.clock_s if local else timestamp))
        return observations


def transfer_facility(source):
    """Synthetic elongated inventory with two changed doors/accesses.

    Preserve 1,106 usable IDs and their restrictions, but reassign row modules
    and topology. This is not another surveyed site or calibrated traffic network.
    """
    usable=sorted((s for s in source.spaces if not s.unavailable),key=lambda s:s.space_id)
    doors=((-35.,-15.),(220.,-15.));exits=((-55.,145.),(255.,-25.))
    spaces=[]
    for i,s in enumerate(usable):
        row,index=divmod(i,79);x=row*16.;y=index*3.
        spaces.append(replace(s,module_id=f'T{row:02d}',x_m=x,y_m=y,latitude=None,longitude=None,
            distance_to_door_1_m=math.dist((x,y),doors[0]),distance_to_door_2_m=math.dist((x,y),doors[1]),
            distance_to_exit_a_m=math.dist((x,y),exits[0]),distance_to_exit_b_m=math.dist((x,y),exits[1])))
    return Facility('transfer_synthetic','Synthetic transfer layout',tuple(spaces),exits,exits,
        synthetic=True,walmart_doors=doors,entry_point_ids=('exit_a','exit_b'),
        exit_point_ids=('exit_a','exit_b'),walmart_door_ids=('door_1','door_2'))
