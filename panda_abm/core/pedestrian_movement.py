"""Network walking and conservative, reserved crossing occupancy."""
import math
from panda_abm.core.urban_traffic import road_agents
from panda_abm.core.states import DriverState
DRIVING={DriverState.SEARCHING,DriverState.TARGETING,DriverState.EXITING}
from panda_abm.environment.pedestrian_geometry import segment_distance,point_segment


def vehicle_sweep_hits(car,model,position,direction,distance,points):
    """Pedestrian clearance against vehicle width/length, not a large centre disk."""
    from panda_abm.core.bay_clearance import rectangle,dimensions,display_position
    from panda_abm.environment.pedestrian_geometry import segment_hits_polygon
    start=display_position(model,position,direction) if hasattr(model,'navigation') else position
    end=(start[0]+direction[0]*distance,start[1]+direction[1]*distance)
    length,width=dimensions(car)
    radius=math.hypot(length+.7,width+.7)/2
    if all(segment_distance(start,end,a,b)>radius for a,b in zip(points,points[1:])):
        return False
    # A 0.35-m pedestrian radius on each side of the vehicle envelope.
    vertices=sorted(set(rectangle(start,direction,length+.7,width+.7)+rectangle(end,direction,length+.7,width+.7)))
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    lower=[];upper=[]
    for p in vertices:
        while len(lower)>1 and cross(lower[-2],lower[-1],p)<=0:lower.pop()
        lower.append(p)
    for p in reversed(vertices):
        while len(upper)>1 and cross(upper[-2],upper[-1],p)<=0:upper.pop()
        upper.append(p)
    polygon=lower[:-1]+upper[:-1]
    return any(segment_hits_polygon(a,b,polygon) for a,b in zip(points,points[1:]))

def start_walk(agent,returning=False):
    points=list(agent.walking_route_data['points']);edges=list(agent.walking_route_data['edges'])
    if returning:points.reverse();edges.reverse()
    agent.walk_points=points;agent.walk_edges=edges;agent.walk_edge_index=0
    agent.walk_position=points[0];agent.walk_phase='to_vehicle' if returning else 'to_door'
    agent.walk_leg_started_s=agent.model.clock_s
    agent.pedestrian_segments=getattr(agent,'pedestrian_segments',[])

def safe_to_cross(agent,points):
    model=agent.model
    if not model.traffic:return True
    duration=sum(math.dist(a,b) for a,b in zip(points,points[1:]))/model.walk_speed_m_per_s
    lookahead=model.search_speed_m_per_s*(duration+2)+model.traffic.vehicle_length_m
    for car in road_agents(model):
        if car.state not in DRIVING:continue
        previous=(car.x_m,car.y_m);left=lookahead
        # Use exactly the same envelope as yielding; inconsistent stop/cross
        # distances create permanent mutual waits.
        from panda_abm.core.traffic import heading
        u=getattr(car,'vehicle_heading',heading(car))
        if math.hypot(*u)<.1:u=(1.,0.)
        if vehicle_sweep_hits(car,model,previous,u,0.,points):return False
        if getattr(model.traffic,'budgets',{}).get(car.driver_id,float('inf'))<=1e-6:
            continue
        for target in car.route:
            length=math.dist(previous,target)
            if length<1e-9:continue
            distance=min(left,length);end=(previous[0]+(target[0]-previous[0])*distance/length,previous[1]+(target[1]-previous[1])*distance/length)
            u=((target[0]-previous[0])/length,(target[1]-previous[1])/length)
            if vehicle_sweep_hits(car,model,previous,u,distance,points):return False
            left-=distance;previous=target
            if left<=0:break
    return True

def safe_step(agent,target,dt):
    model=agent.model
    if not model.traffic:return True
    current=agent.walk_position;distance=math.dist(current,target)
    ratio=min(1.,model.walk_speed_m_per_s*dt/distance) if distance else 0.
    end=tuple(a+(b-a)*ratio for a,b in zip(current,target))
    for car in road_agents(model):
        if car.state not in DRIVING:continue
        pos=(car.x_m,car.y_m);budget=model.traffic.budgets.get(car.driver_id,0.)
        from panda_abm.core.traffic import heading
        direction=getattr(car,'vehicle_heading',heading(car))
        if math.hypot(*direction)<.1:direction=(1.,0.)
        if vehicle_sweep_hits(car,model,pos,direction,0.,[current,end]):return False
        if budget<=1e-7:continue
        for q in car.route:
            d=math.dist(pos,q)
            if d<1e-9:continue
            move=min(d,budget);future=tuple(a+(b-a)*move/d for a,b in zip(pos,q))
            direction=((q[0]-pos[0])/d,(q[1]-pos[1])/d)
            if vehicle_sweep_hits(car,model,pos,direction,move,[current,end]):return False
            budget-=move;pos=q
            if budget<=0:break
    return True

def advance_walk(agent,dt,now):
    model=agent.model;remaining=dt;stamp=now-dt
    reservations=getattr(model,'pedestrian_reservations',None)
    if reservations is None:model.pedestrian_reservations={};reservations=model.pedestrian_reservations
    def record(a,b,duration,waiting=False):
        nonlocal stamp
        if duration<=1e-9:return
        agent.pedestrian_segments.append(dict(phase=agent.walk_phase,start_s=stamp,end_s=stamp+duration,from_m=list(a),to_m=list(b),waiting=waiting,space=agent.chosen_space_id,door=agent.attributes.walmart_door_id,source='simulated_network_walk'))
        stamp+=duration
    while remaining>1e-9 and agent.walk_edge_index<len(agent.walk_edges):
        i=agent.walk_edge_index;edge=agent.walk_edges[i];target=agent.walk_points[i+1]
        reservation=reservations.get(agent.driver_id)
        if edge.get('kind')=='crossing' and reservation is None:
            end=i
            while end+1<len(agent.walk_edges) and agent.walk_edges[end+1].get('kind')=='crossing':end+=1
            crossing=[agent.walk_position]+agent.walk_points[i+1:end+2]
            if not safe_to_cross(agent,crossing):
                record(agent.walk_position,agent.walk_position,remaining,True)
                agent.pedestrian_wait_s=getattr(agent,'pedestrian_wait_s',0.)+remaining
                return False
            reservations[agent.driver_id]=dict(points=crossing,end_index=end,crossing_id=edge['crossing_id'])
        if edge.get('kind')!='crossing' and not safe_step(agent,target,remaining):
            record(agent.walk_position,agent.walk_position,remaining,True)
            agent.pedestrian_wait_s=getattr(agent,'pedestrian_wait_s',0.)+remaining
            return False
        distance=math.dist(agent.walk_position,target)
        if distance<1e-8:agent.walk_edge_index+=1;continue
        duration=min(remaining,distance/model.walk_speed_m_per_s);ratio=duration*model.walk_speed_m_per_s/distance
        point=tuple(a+(b-a)*ratio for a,b in zip(agent.walk_position,target))
        record(agent.walk_position,point,duration);agent.walk_position=point;remaining-=duration
        if math.dist(point,target)<1e-7:
            agent.walk_edge_index+=1
            reservation=reservations.get(agent.driver_id)
            if reservation and agent.walk_edge_index>reservation['end_index']:reservations.pop(agent.driver_id,None)
    return agent.walk_edge_index>=len(agent.walk_edges)

def yield_to_pedestrians(traffic,active,poses):
    reservations=dict(getattr(traffic.model,'pedestrian_reservations',{}))
    for walker in traffic.model.agents:
        if walker.state in (DriverState.WALKING_TO_DESTINATION,DriverState.RETURNING_TO_VEHICLE) and getattr(walker,'walk_position',None) is not None:
            reservations['position_'+walker.driver_id]=dict(points=[walker.walk_position,walker.walk_position],crossing_id='pedestrian_'+walker.driver_id)
    for car in active:
        pos,u=poses[car.driver_id];budget=traffic.budgets[car.driver_id]
        for reservation in reservations.values():
            points=reservation['points']
            def clear(distance):
                if math.hypot(*u)<.1:return True
                return not vehicle_sweep_hits(car,traffic.model,pos,u,distance,points)
            if clear(budget):continue
            low,high=0.,budget
            for _ in range(14):
                mid=(low+high)/2
                if clear(mid):low=mid
                else:high=mid
            traffic.budgets[car.driver_id]=low;car.traffic_reason='pedestrian_crossing';car.traffic_blocker=reservation['crossing_id']

def crossing_blocks_entry(model,point):
    if any(a.state in (DriverState.WALKING_TO_DESTINATION,DriverState.RETURNING_TO_VEHICLE) and getattr(a,'walk_position',None) is not None and math.dist(point,a.walk_position)<4 for a in model.agents):return True
    return any(point_segment(point,a,b)<4 for r in getattr(model,'pedestrian_reservations',{}).values() for a,b in zip(r['points'],r['points'][1:]))


def completion_padding(model):
    if model.facility.pedestrian_network is None:return 0.
    distances=[model.facility.walking_network.distance(s.space_id,d) for d in model.facility.walmart_door_ids for s in model.facility.spaces]
    longest=max((d for d in distances if math.isfinite(d)),default=0.)
    demand=getattr(getattr(model,'through_traffic',None),'demand_s',0) if getattr(getattr(model,'through_traffic',None),'level','off')!='off' else 0
    return demand+2*longest/model.walk_speed_m_per_s
