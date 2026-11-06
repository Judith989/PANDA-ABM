"""Aggregate current aisle information and a common preference-based route rule.

The planning rule sees counts plus static geometry/restrictions, not the IDs or
locations of the remotely free stalls. Stall choice remains local and uses the
selected M0/M1/M2 model. Counts are personalized to static feasibility (vehicle,
permit and walking limit); they are not counts of future claim successes.
"""
from dataclasses import dataclass
import numpy as np
from panda_abm.behavior.decision.transforms import FEATURE_SPECS
from panda_abm.environment.perception import PerceivedSpace

INFORMATION_MODES=('unaided','aisle','space')


@dataclass(frozen=True)
class AisleInformation:
    observed_at_s: float
    free_counts: dict[str,int]
    compatible_capacity: dict[str,int]


class AisleInformationService:
    def __init__(self,model):
        self.model=model
        self._static={}

    def _prepare(self,agent):
        if agent.driver_id in self._static:return self._static[agent.driver_id]
        model=self.model
        static=model.choice_set_builder.build(agent,[PerceivedSpace(s,0.,False,not s.unavailable) for s in model.facility.spaces])
        grouped={}
        for s in static:grouped.setdefault(model.navigation.space_aisle[s.space_id],[]).append(s)
        result={}
        for aisle,spaces in grouped.items():
            walk=np.array([model.facility.walking_distance(s,agent.attributes) for s in spaces])
            exit_id=agent.attributes.preferred_exit_id
            features=dict(approach_time_s=0.,search_time_s=0.,walking_distance_m=walk,
                exit_distance_m=np.array([(s.exit_distance(exit_id) or 0.) if exit_id else 0. for s in spaces]),
                price_per_hour=np.array([s.price_per_hour for s in spaces]),
                accessibility_match=np.array([float(s.accessible and agent.attributes.accessibility_eligibility) for s in spaces]),
                rule_risk=np.array([float(bool((s.accessible and not agent.attributes.accessibility_eligibility) or
                    (s.reserved_type and agent.attributes.permit_type!=(s.permit_requirement or s.reserved_type)))) for s in spaces]),
                availability_probability=0.,familiarity=agent.attributes.local_familiarity)
            score=0.
            for name,spec in FEATURE_SPECS.items():
                normalized=np.clip(np.asarray(features[name])/spec.scale,0.,1.)
                oriented=normalized if spec.direction==1 else 1.-normalized
                score+=getattr(agent.parameters,spec.weight_name)*float(np.mean(oriented))
            result[aisle]=(tuple(s.space_id for s in spaces),score)
        self._static[agent.driver_id]=result
        return result

    def snapshot(self,agent):
        static=self._prepare(agent)
        return AisleInformation(self.model.clock_s,
            {aisle:sum(not(self.model.space_states[sid].occupied or self.model.space_states[sid].unavailable) for sid in ids)
             for aisle,(ids,_) in static.items()},
            {aisle:sum(not self.model.space_states[sid].unavailable for sid in ids) for aisle,(ids,_) in static.items()})

    def plan_search(self,agent,report):
        """Route to/through a promising aisle after local offers were declined.

        Static mean oriented utility plus free fraction represents exchangeable
        unknown stalls. Search/approach costs use the same normalizations as
        utility. This common deterministic planning heuristic is deliberately
        independent of decision-model labels and uses no assigned personas.
        """
        nav=self.model.navigation
        positive=[a for a,count in report.free_counts.items() if count>0]
        if not positive:
            if agent.information_aisle_id is not None:agent.route=[];agent.patrol_goal=None
            agent.information_aisle_id=None
            return False
        if agent.information_aisle_id in positive and agent.route:return True
        static=self._prepare(agent)
        targets={n for a in positive for n in nav.aisle_nodes[a]}
        distances=nav.distances((agent.x_m,agent.y_m),targets,heading=getattr(agent,'routing_heading',None))
        def score(aisle):
            approach=min(distances[n] for n in nav.aisle_nodes[aisle])/self.model.search_speed_m_per_s
            value=static[aisle][1]
            value-=agent.parameters.beta_approach*min(approach/FEATURE_SPECS['approach_time_s'].scale,1.)
            value-=agent.parameters.beta_search*min(agent.search_time_s/FEATURE_SPECS['search_time_s'].scale,1.)
            value+=agent.parameters.beta_availability*report.free_counts[aisle]/report.compatible_capacity[aisle]
            return value
        # Stable static ID tie break, never hidden free-stall position.
        aisle=min(positive,key=lambda a:(-score(a),min(distances[n] for n in nav.aisle_nodes[a]),a))
        entry,other=sorted(nav.aisle_nodes[aisle],key=lambda n:(distances[n],n))
        agent.route=nav.route((agent.x_m,agent.y_m),entry,heading=getattr(agent,'routing_heading',None))+nav.route(nav.positions[entry],other)
        agent.patrol_goal=other
        agent.information_aisle_id=aisle
        agent.information_route_changes+=1
        agent.log('InformationSearchAreaSelected',details=dict(aisle_id=aisle,free_count=report.free_counts[aisle],
            compatible_capacity=report.compatible_capacity[aisle],report_time_s=report.observed_at_s,
            area_score=score(aisle),entry_node=entry,end_node=other))
        return True
