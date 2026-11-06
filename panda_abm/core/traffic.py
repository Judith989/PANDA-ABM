"""Optional, uncalibrated aisle traffic: following, junction yielding and queues.

Two directional lanes share the inferred centreline. Longitudinal positions stay
on that graph; a right-hand offset is supplied for display. This is a kinematic
queue model, not a calibrated road-traffic or collision-dynamics simulator.
"""
from __future__ import annotations

import math
from collections import Counter
from panda_abm.core.states import DriverState
from panda_abm.core.urban_traffic import road_agents,apply_controls

DRIVING = {DriverState.SEARCHING, DriverState.TARGETING, DriverState.EXITING}


def heading(agent):
    for x, y in agent.route:
        dx, dy = x-agent.x_m, y-agent.y_m
        norm = math.hypot(dx, dy)
        if norm > 1e-3:
            return dx/norm, dy/norm
    return getattr(agent, 'traffic_heading', (0., 0.))


def crossing(a, u, b, v):
    """Forward distances to intersection of two directed lines, if nonparallel."""
    cross = u[0]*v[1]-u[1]*v[0]
    if abs(cross) < 1e-7:
        return None
    dx, dy = b[0]-a[0], b[1]-a[1]
    return (dx*v[1]-dy*v[0])/cross, (dx*u[1]-dy*u[0])/cross


class AisleTraffic:
    vehicle_length_m = 5.45
    minimum_gap_m = 2.
    junction_clearance_m = 5.
    congestion_min_duration_s = 5.

    def __init__(self, model):
        self.model = model
        self.budgets = {}
        self.episodes = []
        self.open_episodes = {}
        self.jam_episodes = []
        self.open_jam_episodes = {}
        self.cumulative_delay_s = 0.
        self.aisle_delay_s = Counter()
        self.aisle_peak_queue = Counter()

    def can_enter(self, agent):
        # Arrivals wait outside the modeled road until the entry has clearance.
        from panda_abm.core.pedestrian_movement import crossing_blocks_entry
        if crossing_blocks_entry(self.model,(agent.x_m,agent.y_m)):return False
        return not any(a is not agent and a.state in DRIVING and
                       math.dist((a.x_m, a.y_m), (agent.x_m, agent.y_m)) <
                       self.vehicle_length_m+self.minimum_gap_m
                       for a in road_agents(self.model))

    def aisle_at(self, point):
        nav = self.model.navigation
        def distance(ends):
            a, b = (nav.positions[n] for n in ends)
            dx, dy = b[0]-a[0], b[1]-a[1]
            t = max(0., min(1., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy)))
            return math.dist(point, (a[0]+t*dx, a[1]+t*dy))
        key = min(nav.aisle_nodes, key=lambda k: distance(nav.aisle_nodes[k]))
        return key if distance(nav.aisle_nodes[key]) <= 8. else 'cross_aisle'

    def begin_tick(self):
        active = sorted((a for a in road_agents(self.model) if a.state in DRIVING), key=lambda a:a.driver_id)
        self.budgets = {}
        poses = {a.driver_id: ((a.x_m, a.y_m), heading(a)) for a in active}
        desired = {}
        straight_ranges = {}
        for a in active:
            a.traffic_heading = poses[a.driver_id][1]
            a.traffic_reason = a.traffic_blocker = None
            a.traffic_ahead = a.traffic_behind = a.traffic_gap_m = None
            a.traffic_nearby = []
            # Reassess conflicts before turning onto a different segment.
            straight = 0.
            previous = (a.x_m, a.y_m)
            for point in a.route:
                dx, dy = point[0]-previous[0], point[1]-previous[1]
                length = math.hypot(dx, dy)
                if length > 1e-7 and (dx*a.traffic_heading[0]+dy*a.traffic_heading[1])/length < .999:
                    break
                straight += length
                previous = point
            desired[a.driver_id] = min(self.model.search_speed_m_per_s*self.model.integration_seconds, straight)
            straight_ranges[a.driver_id] = straight
            self.budgets[a.driver_id] = desired[a.driver_id]
        apply_controls(self,active,poses)
        # First establish downstream capacity. A car blocked behind a queue
        # cannot reserve a junction that it cannot enter.
        for a in active:
            pos,u = poses[a.driver_id]
            ahead,behind = [],[]
            for b in active:
                if b is a:continue
                other,v = poses[b.driver_id]
                dx,dy = other[0]-pos[0],other[1]-pos[1]
                distance = math.hypot(dx,dy)
                if distance <= self.model.perception_radius_m:
                    a.traffic_nearby.append(dict(driver=b.driver_id,distance_m=distance))
                along,across = dx*u[0]+dy*u[1],abs(dx*u[1]-dy*u[0])
                if u[0]*v[0]+u[1]*v[1] > .8 and across < 1.5:
                    if along > 1e-6:ahead.append((along,b.driver_id))
                    elif along < -1e-6:behind.append((-along,b.driver_id))
            if ahead:
                distance,driver = min(ahead)
                if distance <= self.model.perception_radius_m:
                    a.traffic_ahead,a.traffic_gap_m = driver,max(0.,distance-self.vehicle_length_m)
                limit = max(0.,distance-self.vehicle_length_m-self.minimum_gap_m)
                if limit < self.budgets[a.driver_id]:
                    self.budgets[a.driver_id] = limit
                    a.traffic_reason,a.traffic_blocker = 'following_vehicle',driver
            if behind and min(behind)[0] <= self.model.perception_radius_m:
                a.traffic_behind = min(behind)[1]
        clearance = self.vehicle_length_m+self.minimum_gap_m
        turns = {}
        # Do not enter a turn unless its outgoing lane has room. This prevents
        # a merging vehicle from inserting itself inside an existing queue.
        for a in active:
            pos,u = poses[a.driver_id]
            straight = straight_ranges[a.driver_id]
            if straight > desired[a.driver_id]+clearance:continue
            turn=(pos[0]+u[0]*straight,pos[1]+u[1]*straight)
            outgoing=None
            reached=False
            for point in a.route:
                if math.dist(point,turn)<1e-6:
                    reached=True;continue
                if reached:
                    dx,dy=point[0]-turn[0],point[1]-turn[1]
                    length=math.hypot(dx,dy)
                    if length>1e-7:
                        outgoing=(dx/length,dy/length);break
            nav=getattr(self.model,'navigation',None)
            if nav is not None and hasattr(nav,'_point_nodes'):
                node=nav._point_nodes.get(tuple(round(x,8) for x in turn))
                if node is not None and nav.graph.degree(node)>2:
                    # Patrol routes may end here before the driver chooses its
                    # next direction. Reserve entry even without an outgoing
                    # leg, so opposite cars cannot stop on the same junction.
                    turns[a.driver_id]=turn
            if outgoing is None:continue
            if u[0]*outgoing[0]+u[1]*outgoing[1]<.8:
                turns[a.driver_id]=turn
            if hasattr(self.model,'facility') and hasattr(self.model,'navigation') and straight>clearance:
                from panda_abm.core.bay_clearance import limit_motion
                if limit_motion(a,outgoing,1e-4,origin=turn)<1e-4:
                    limit=max(0.,straight-clearance)
                    self.budgets[a.driver_id]=min(self.budgets[a.driver_id],limit)
            for b in active:
                if b is a:continue
                other,v=poses[b.driver_id]
                dx,dy=other[0]-turn[0],other[1]-turn[1]
                along=dx*outgoing[0]+dy*outgoing[1]
                across=abs(dx*outgoing[1]-dy*outgoing[0])
                if 0 <= along < clearance and across<1.5 and v[0]*outgoing[0]+v[1]*outgoing[1]>.8:
                    limit=max(0.,straight-clearance)
                    if limit<self.budgets[a.driver_id]:
                        self.budgets[a.driver_id]=limit
                        a.traffic_reason,a.traffic_blocker='downstream_queue',b.driver_id
        # A maneuver is an obstruction, not a competing right-of-way request.
        for a in active:
            pos,u=poses[a.driver_id]
            for b in active:
                if b is a or b.state!=DriverState.TARGETING or b.route or b.maneuver_remaining_s<=0:continue
                node=self.model.navigation.space_nodes[b.chosen_space_id]
                roads=list(self.model.navigation.graph.neighbors(node))
                if not roads:continue
                road=self.model.navigation.positions[roads[0]]
                dx,dy=road[0]-pos[0],road[1]-pos[1]
                along,across=dx*u[0]+dy*u[1],abs(dx*u[1]-dy*u[0])
                if -1.<=along<=desired[a.driver_id]+clearance and across<2.:
                    limit=max(0.,along-clearance)
                    if limit<self.budgets[a.driver_id]:
                        self.budgets[a.driver_id]=limit
                        a.traffic_reason,a.traffic_blocker='parking_maneuver',b.driver_id
        # Select junction priority only among cars that can physically advance.
        # A nominal winner blocked by another car's footprint must not hold all
        # other approaches indefinitely while failing its own movement check.
        if hasattr(self.model,'facility') and hasattr(self.model,'navigation'):
            from panda_abm.core.bay_clearance import limit_motion
            for a in active:
                budget=self.budgets[a.driver_id]
                if budget>1e-7:
                    self.budgets[a.driver_id]=min(budget,limit_motion(a,poses[a.driver_id][1],budget))
        # Coordinate each connected group of nearby crossing conflicts with ONE
        # priority order. Pair-dependent 'already crossed' rankings can create a
        # circular yield at closely spaced inferred junctions.
        parent={a.driver_id:a.driver_id for a in active}
        def find(k):
            while parent[k]!=k:
                parent[k]=parent[parent[k]];k=parent[k]
            return k
        conflicts=[]
        distances={a.driver_id:float('inf') for a in active}
        for i,a in enumerate(active):
            pos,u=poses[a.driver_id]
            for b in active[i+1:]:
                other,v=poses[b.driver_id]
                alignment=u[0]*v[0]+u[1]*v[1]
                # Opposing through movements can pass, but opposing turns at
                # one junction must not occupy its turning envelope together.
                if abs(alignment)>.8:
                    if alignment>0 or a.driver_id not in turns or b.driver_id not in turns:continue
                    if math.dist(turns[a.driver_id],turns[b.driver_id])>2.:continue
                    hit=(straight_ranges[a.driver_id],straight_ranges[b.driver_id])
                else:
                    hit=crossing(pos,u,other,v)
                if not hit:continue
                da,db=hit
                if not (-clearance<da<desired[a.driver_id]+clearance and
                        -clearance<db<desired[b.driver_id]+clearance and
                        da<=straight_ranges[a.driver_id]+1e-7 and db<=straight_ranges[b.driver_id]+1e-7):continue
                conflicts.append((a,b,da,db))
                parent[find(a.driver_id)]=find(b.driver_id)
                distances[a.driver_id]=min(distances[a.driver_id],abs(da))
                distances[b.driver_id]=min(distances[b.driver_id],abs(db))
        groups={}
        by_id={a.driver_id:a for a in active}
        for a,b,_,_ in conflicts:
            group=groups.setdefault(find(a.driver_id),set())
            group.update([a.driver_id,b.driver_id])
        old_leaders=getattr(self,'priority_leaders',set())
        winners={}
        for root,members in groups.items():
            eligible=[id for id in members if self.budgets[id]>1e-7]
            if not eligible:continue
            winner=min(eligible,key=lambda id:(
                distances[id]>self.vehicle_length_m/2,
                distances[id] if distances[id]<=self.vehicle_length_m/2 else 0.,
                id not in old_leaders,-getattr(by_id[id],'traffic_wait_s',0.),id))
            winners[root]=winner
        self.priority_leaders=set(winners.values())
        for a,b,da,db in conflicts:
            winner=winners.get(find(a.driver_id))
            if winner is None:continue
            for agent,distance in ((a,da),(b,db)):
                if agent.driver_id==winner:continue
                limit=max(0.,distance-clearance)
                if limit<self.budgets[agent.driver_id]:
                    self.budgets[agent.driver_id]=limit
                    agent.traffic_reason,agent.traffic_blocker='junction_yield',winner

        from panda_abm.core.pedestrian_movement import yield_to_pedestrians
        yield_to_pedestrians(self,active,poses)

    def distance_budget(self, agent, dt):
        return min(self.model.search_speed_m_per_s*dt,
                   self.budgets.get(agent.driver_id, self.model.search_speed_m_per_s*dt))

    def end_tick(self):
        dt = self.model.integration_seconds
        queues = Counter()
        causes = {}
        queued_delay = Counter()
        for a in road_agents(self.model):
            active = a.state in DRIVING
            reason = getattr(a, 'traffic_reason', None) if active and a.route else None
            a.traffic_wait_s = getattr(a, 'traffic_wait_s', 0.)+dt if reason else 0.
            if reason:
                delay = max(0., dt-getattr(a, 'traffic_speed_m_s', 0.)*dt/self.model.search_speed_m_per_s)
                a.traffic_delay_s = getattr(a, 'traffic_delay_s', 0.)+delay
                self.cumulative_delay_s += delay
                aisle = self.aisle_at((a.x_m, a.y_m))
                self.aisle_delay_s[aisle] += delay
                if getattr(a, 'traffic_speed_m_s', 0.) < .5:
                    queues[aisle] += 1
                    queued_delay[aisle] += delay
                    causes.setdefault(aisle, Counter())[reason] += 1
        now = self.model.clock_s+dt
        for aisle,count in queues.items():
            self.aisle_peak_queue[aisle]=max(self.aisle_peak_queue[aisle],count)
        self._update_episode_group(self.episodes,self.open_episodes,queues,causes,queued_delay,now,dt,1)
        self._update_episode_group(self.jam_episodes,self.open_jam_episodes,queues,causes,queued_delay,now,dt,2)
        self.queues=dict(queues)

    def _update_episode_group(self,completed,opened,queues,causes,queued_delay,now,dt,minimum):
        qualifying={aisle:count for aisle,count in queues.items() if count>=minimum}
        for aisle,count in qualifying.items():
            if aisle not in opened:
                opened[aisle]=dict(aisle=aisle,start_s=now-dt,peak_queue=0,causes=Counter(),
                    cause_vehicle_seconds=Counter(),cause_active_seconds=Counter(),queued_vehicle_delay_s=0.,minimum_queued_vehicles=minimum)
            episode=opened[aisle]
            episode['peak_queue']=max(episode['peak_queue'],count)
            episode['causes'].update(causes[aisle])
            episode['cause_vehicle_seconds'].update({k:v*dt for k,v in causes[aisle].items()})
            episode['cause_active_seconds'].update({k:dt for k in causes[aisle]})
            episode['queued_vehicle_delay_s']+=queued_delay[aisle]
        for aisle in set(opened)-set(qualifying):
            episode=opened.pop(aisle);episode['end_s']=now-dt
            episode['duration_s']=episode['end_s']-episode['start_s']
            for field in ('causes','cause_vehicle_seconds','cause_active_seconds'):episode[field]=dict(episode[field])
            episode['multi_vehicle_queue']=episode['peak_queue']>=2
            if episode['duration_s']>=self.congestion_min_duration_s:completed.append(episode)

    def snapshot(self):
        now=self.model.clock_s
        def records(completed,opened):
            ongoing=[dict(e,end_s=None,duration_s=max(0.,now-e['start_s']),causes=dict(e['causes']),
                cause_vehicle_seconds=dict(e['cause_vehicle_seconds']),cause_active_seconds=dict(e['cause_active_seconds']),
                multi_vehicle_queue=e['peak_queue']>=2) for e in opened.values() if now-e['start_s']>=self.congestion_min_duration_s]
            return sorted(completed+ongoing,key=lambda e:(e['start_s'],e['aisle'],e['end_s'] if e['end_s'] is not None else float('inf')))
        return dict(enabled=True,model='kinematic_aisle_v1',
            parameters=dict(vehicle_length_m=self.vehicle_length_m,minimum_gap_m=self.minimum_gap_m,integration_seconds=self.model.integration_seconds,
                display_lane_offset_m=1.2,queue_speed_threshold_m_s=.5,congestion_min_duration_s=self.congestion_min_duration_s,jam_minimum_queued_vehicles=2),
            definition='Delay episode: at least one traffic-constrained vehicle below 0.5 m/s in an aisle for at least 5 s',
            jam_definition='At least two traffic-constrained vehicles below 0.5 m/s in an aisle continuously for at least 5 s',
            queues=getattr(self,'queues',{}),cumulative_delay_s=self.cumulative_delay_s,aisle_delay_s=dict(self.aisle_delay_s),
            aisle_peak_queue=dict(self.aisle_peak_queue),episodes=records(self.episodes,self.open_episodes),
            jam_episodes=records(self.jam_episodes,self.open_jam_episodes))

    def driver_view(self, agent):
        moving = agent.state in DRIVING
        u = getattr(agent,'vehicle_heading',getattr(agent, 'traffic_heading', (0., 0.))) if moving else (0., 0.)
        return dict(speed_m_s=getattr(agent, 'traffic_speed_m_s', 0.) if moving else 0.,
                    ahead=getattr(agent, 'traffic_ahead', None), behind=getattr(agent, 'traffic_behind', None),
                    gap_m=getattr(agent, 'traffic_gap_m', None), reason=getattr(agent, 'traffic_reason', None),
                    blocker=getattr(agent, 'traffic_blocker', None), delay_s=getattr(agent, 'traffic_delay_s', 0.),
                    nearby=getattr(agent,'traffic_nearby',[]) if moving else [],
                    aisle=self.aisle_at((agent.x_m, agent.y_m)) if moving else None,
                    display_offset_m=[u[1]*1.2, -u[0]*1.2],
                    last_candidates=list(agent.last_candidate_space_ids[:20]),
                    candidate_count=len(agent.last_candidate_space_ids),
                    observation_s=getattr(agent,'last_observation_s',None),
                    visible_count=len(getattr(agent,'last_visible_space_ids',[])),
                    visible_free_count=len(getattr(agent,'last_visible_free_space_ids',[])))
