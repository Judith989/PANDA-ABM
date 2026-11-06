"""Local maneuver exclusion; information reports never reserve parking supply."""
import math

def access_node(model,space_id):
    nav=model.navigation;stall=nav.space_nodes[space_id]
    raw=model.facility.aisle_network
    if raw:
        key=raw['space_access'][space_id]['node'];point=raw['nodes'][key]
        if math.dist(point,nav.positions[stall])>1e-6:return nav._node(point)
    neighbors=list(nav.graph.neighbors(stall))
    neighbors=[n for n in neighbors if n!=stall]
    return min(neighbors,key=lambda n:(n in set(nav.space_nodes.values()),math.dist(nav.positions[n],nav.positions[stall]),n)) if neighbors else stall

def drop_reservation(agent):
    held=getattr(agent.model,'bay_maneuvers',{})
    for sid,owner in list(held.items()):
        if owner==agent.driver_id:held.pop(sid)

def begin_maneuver(agent):
    model=agent.model;sid=agent.chosen_space_id
    if not hasattr(model,'bay_maneuvers'):model.bay_maneuvers={}
    owner=model.bay_maneuvers.get(sid)
    if not model.resource_manager.is_available(sid) or owner not in (None,agent.driver_id) or not parking_clear(agent):return False
    point=model.navigation.positions[model.navigation.space_nodes[sid]]
    stage=model.navigation.positions[access_node(model,sid)]
    distance=math.dist(stage,point)
    if distance>1e-6:
        direction=((point[0]-stage[0])/distance,(point[1]-stage[1])/distance)
        if limit_motion(agent,direction,distance,origin=stage,static_only=True)<distance-1e-6:
            return False
    model.bay_maneuvers[sid]=agent.driver_id
    agent.bay_entry_started=True
    point=model.navigation.positions[model.navigation.space_nodes[sid]]
    agent.route=[point];agent.log('BayManeuverStarted',space_id=sid)
    return True

def departure_cleared(agent):
    sid=getattr(agent,'departure_space_id',None)
    if not sid:return True
    s=agent.model.facility.space_by_id[sid]
    # Conservative footprint envelope includes the largest displayed vehicle.
    # ParkingSpace does not retain display headings: use raw environment slot metadata when supplied.
    data=getattr(agent.model.facility,'aisle_network',None) or {}
    geometry=data.get('bay_geometry',{}).get(sid,{})
    angle=math.radians(geometry.get('heading_deg',0))
    if geometry.get('heading_reference')=='clockwise_from_north':angle=math.pi/2-angle
    dx,dy=agent.x_m-s.x_m,agent.y_m-s.y_m
    along=abs(dx*math.cos(angle)+dy*math.sin(angle));across=abs(-dx*math.sin(angle)+dy*math.cos(angle))
    return along>(geometry.get('length_m',4.9)+5.45)/2+.3 or across>(geometry.get('width_m',2.06)+2.05)/2+.3

def release_departure_if_clear(agent,force=False):
    sid=getattr(agent,'departure_space_id',None)
    if sid and (force or departure_cleared(agent)):
        agent.parking_released_s=agent.model.clock_s
        agent.model.release_parking(agent,sid);agent.departure_space_id=None
        drop_reservation(agent)

def rectangle(position,heading,length,width):
    x,y=position;ux,uy=heading;vx,vy=-uy,ux
    return [(x+i*length/2*ux+j*width/2*vx,y+i*length/2*uy+j*width/2*vy) for i,j in ((-1,-1),(-1,1),(1,1),(1,-1))]

def overlaps(a,b):
    for p,q in ((a[0],a[1]),(a[1],a[2]),(b[0],b[1]),(b[1],b[2])):
        axis=(-(q[1]-p[1]),q[0]-p[0]);aa=[x*axis[0]+y*axis[1] for x,y in a];bb=[x*axis[0]+y*axis[1] for x,y in b]
        if max(aa)<=min(bb)+1e-8 or max(bb)<=min(aa)+1e-8:return False
    return True

DIMENSIONS={'compact':(3.9,1.72),'sedan':(4.55,1.82),'suv':(4.75,1.94),'van':(5.15,2.),'truck':(5.45,2.02)}

def dimensions(agent):return DIMENSIONS.get(getattr(getattr(agent,'attributes',None),'vehicle_type','sedan'),(4.55,1.82))

def parking_clear(agent):
    model=agent.model;sid=agent.chosen_space_id;s=model.facility.space_by_id[sid]
    geometry=(model.facility.aisle_network or {}).get('bay_geometry',{})
    def shape(space,l,w):
        g=geometry.get(space.space_id,{});angle=math.radians(g.get('heading_deg',0))
        if g.get('heading_reference')=='clockwise_from_north':angle=math.pi/2-angle
        return rectangle((space.x_m,space.y_m),(math.cos(angle),math.sin(angle)),l+.1,w+.1)
    target=shape(s,*dimensions(agent))
    for other,state in model.space_states.items():
        reservation=getattr(model,'bay_maneuvers',{}).get(other)
        if other==sid or (not state.occupied and not reservation):continue
        t=model.facility.space_by_id[other]
        if math.dist((s.x_m,s.y_m),(t.x_m,t.y_m))>8:continue
        owner=next((a for a in model.agents if a.driver_id==(reservation or state.occupant_id)),None)
        if overlaps(target,shape(t,*(dimensions(owner) if owner else (5.45,2.02)))):return False
    return True

def display_position(model,point,u):
    nav=model.navigation
    # Match Cesium's right-hand display offset, only on non-bay road edges.
    from panda_abm.environment.pedestrian_geometry import point_segment
    cells=getattr(model,'_clearance_road_cells',None)
    if cells is None:
        cells={};stalls=set(nav.space_nodes.values())
        for a,b in nav._edges:
            if a in stalls or b in stalls:continue
            p,q=nav.positions[a],nav.positions[b]
            for x in range(math.floor(min(p[0],q[0])/10),math.floor(max(p[0],q[0])/10)+1):
                for y in range(math.floor(min(p[1],q[1])/10),math.floor(max(p[1],q[1])/10)+1):cells.setdefault((x,y),[]).append((a,b))
        model._clearance_road_cells=cells
    for a,b in cells.get((math.floor(point[0]/10),math.floor(point[1]/10)),()):
        p,q=nav.positions[a],nav.positions[b];length=math.dist(p,q)
        if length and point_segment(point,p,q)<1e-4 and abs((q[0]-p[0])*u[0]+(q[1]-p[1])*u[1])/length>.99:return (point[0]+u[1]*1.2,point[1]-u[0]*1.2)
    return point

def limit_motion(agent,direction,distance,origin=None,static_only=False):
    """Check a sampled swept vehicle footprint against actual occupied vehicles."""
    from panda_abm.core.states import DriverState
    from panda_abm.core.urban_traffic import road_agents
    model=agent.model
    if not getattr(model,'traffic',None):return distance
    geometry=(model.facility.aisle_network or {}).get('bay_geometry',{})
    blockers=[];point=origin if origin is not None else (agent.x_m,agent.y_m);own=getattr(agent,'departure_space_id',None)
    # Occupied bays include background cars, which are not driving agents.
    cells=getattr(model,'_clearance_bay_cells',None)
    if cells is None:
        cells={}
        for s in model.facility.spaces:cells.setdefault((math.floor(s.x_m/10),math.floor(s.y_m/10)),[]).append(s.space_id)
        model._clearance_bay_cells=cells;model._clearance_agents={a.driver_id:a for a in model.agents}
    radius=distance+10;near=[]
    for x in range(math.floor((point[0]-radius)/10),math.floor((point[0]+radius)/10)+1):
        for y in range(math.floor((point[1]-radius)/10),math.floor((point[1]+radius)/10)+1):near.extend(cells.get((x,y),()))
    for sid in near:
        state=model.space_states[sid]
        if not state.occupied or sid==own:continue
        s=model.facility.space_by_id[sid]
        if math.dist(point,(s.x_m,s.y_m))>distance+10:continue
        g=geometry.get(sid,{});angle=math.radians(g.get('heading_deg',0))
        if g.get('heading_reference')=='clockwise_from_north':angle=math.pi/2-angle
        owner=model._clearance_agents.get(state.occupant_id)
        l,w=dimensions(owner) if owner else (5.45,2.02)
        blockers.append((rectangle((s.x_m,s.y_m),(math.cos(angle),math.sin(angle)),l+.1,w+.1),'occupied_bay',sid))
    for other in ([] if static_only else road_agents(model)):
        if other is agent or other.state not in (DriverState.SEARCHING,DriverState.TARGETING,DriverState.EXITING):continue
        if math.dist(point,(other.x_m,other.y_m))>distance+10:continue
        from panda_abm.core.traffic import heading
        # A stopped car has not already rotated to its next route leg. Using its
        # intended turn here creates a phantom footprint that can block both
        # approaches before either vehicle has physically made the turn.
        u=getattr(other,'vehicle_heading',heading(other))
        if math.hypot(*u)<.1:u=getattr(other,'traffic_heading',(1.,0.))
        if math.hypot(*u)<.1:u=(1.,0.)
        l,w=dimensions(other);pos=display_position(model,(other.x_m,other.y_m),u)
        blockers.append((rectangle(pos,u,l+.1,w+.1),'vehicle_clearance',other.driver_id))
    buildings=(model.facility.aisle_network or {}).get('building_footprints_m',{})
    nearby_buildings=[]
    for key,poly in buildings.items():
        if min(p[0] for p in poly)-10-distance<=point[0]<=max(p[0] for p in poly)+10+distance and min(p[1] for p in poly)-10-distance<=point[1]<=max(p[1] for p in poly)+10+distance:nearby_buildings.append((key,poly))
    if not blockers and not nearby_buildings:return distance
    l,w=dimensions(agent);steps=max(1,math.ceil(distance/.2));last=0.
    for i in range(steps+1):
        d=distance*i/steps;p=(point[0]+direction[0]*d,point[1]+direction[1]*d)
        shape=rectangle(display_position(model,p,direction),direction,l+.1,w+.1)
        from panda_abm.environment.pedestrian_geometry import segment_hits_polygon,inside
        for key,poly in nearby_buildings:
            if any(segment_hits_polygon(a,b,poly) for a,b in zip(shape,shape[1:]+shape[:1])) or any(inside(q,shape) for q in poly):
                agent.traffic_reason='building_clearance';agent.traffic_blocker=key
                agent.clearance_blocks=getattr(agent,'clearance_blocks',0)+1
                return last
        for obstacle,cause,key in blockers:
            if overlaps(shape,obstacle):
                agent.traffic_reason=cause;agent.traffic_blocker=key
                agent.clearance_blocks=getattr(agent,'clearance_blocks',0)+1
                return last
        last=d
    return distance
