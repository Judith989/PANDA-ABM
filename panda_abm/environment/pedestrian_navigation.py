"""Validated pedestrian routing. Configured networks never fall back to straight lines."""
import math
import networkx as nx
from panda_abm.environment.pedestrian_geometry import ObstacleIndex,bay_polygon

class PedestrianNetwork:
    def __init__(self,data):
        self.data=data;self.nodes=data['nodes'];self.graph=nx.Graph();self.graph.add_nodes_from(self.nodes);self.cache={}
        for edge in data['edges']:
            a,b=edge['from'],edge['to'];self.graph.add_edge(a,b,weight=math.dist(self.nodes[a],self.nodes[b]),kind=edge['kind'],source=edge.get('source','unknown'),crossing_id=edge.get('crossing_id'))
    def _target(self,target):
        if target not in self.cache:self.cache[target]=nx.dijkstra_predecessor_and_distance(self.graph,target)
        return self.cache[target]
    def route(self,space_id,destination_id):
        source=self.data['space_access'].get(space_id);target=self.data['destination_access'].get(destination_id)
        if not source or not target:return None
        parents,lengths=self._target(target);start=source['node']
        if start not in lengths:return None
        nodes=[start]
        while nodes[-1]!=target:nodes.append(parents[nodes[-1]][0])
        prefix=[tuple(p) for p in source['points']];points=prefix+[tuple(self.nodes[n]) for n in nodes[1:]]
        kinds=[dict(kind='bay_access',crossing_id=None)]*(len(prefix)-1)
        kinds += [dict(self.graph[a][b]) for a,b in zip(nodes,nodes[1:])]
        return dict(points=points,edges=kinds,distance_m=sum(math.dist(a,b) for a,b in zip(points,points[1:])))
    def distance(self,space_id,destination_id):
        source=self.data['space_access'].get(space_id);target=self.data['destination_access'].get(destination_id)
        if not source or not target:return math.inf
        _,lengths=self._target(target)
        if source['node'] not in lengths:return math.inf
        return lengths[source['node']]+sum(math.dist(a,b) for a,b in zip(source['points'],source['points'][1:]))

_VALIDATED=set()

def validate_pedestrian_network(raw):
    data=raw.get('pedestrian_network')
    if data is None:return
    import hashlib,json
    digest=hashlib.sha256(json.dumps([data,raw.get('buildings',[]),raw.get('pedestrian_road_areas',[]),raw['slots'],raw['walmart_doors']],sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if digest in _VALIDATED:return
    if data.get('road_polygons',[])!=raw.get('pedestrian_road_areas',data.get('road_polygons',[])):raise ValueError('Pedestrian road masks differ from configured road areas')
    if not isinstance(data,dict) or not isinstance(data.get('nodes'),dict) or not 1<=len(data['nodes'])<=50000:raise ValueError('Invalid pedestrian nodes')
    nodes=data['nodes']
    for k,p in nodes.items():
        if not isinstance(k,str) or not isinstance(p,list) or len(p)!=2 or any(type(v) not in (float,int) or not math.isfinite(v) for v in p):raise ValueError('Invalid pedestrian coordinate')
    edges=data.get('edges');slots={s['id']:s for s in raw['slots']};doors={d['id'] for d in raw['walmart_doors']}
    if not isinstance(edges,list) or len(edges)>150000:raise ValueError('Invalid pedestrian edges')
    obstacles=ObstacleIndex([(b['id'],b['footprint_m']) for b in raw.get('buildings',[])]+[(sid,bay_polygon(s)) for sid,s in slots.items()])
    road=ObstacleIndex([(str(i),p) for i,p in enumerate(data.get('road_polygons',[]))])
    seen=set()
    for edge in edges:
        a,b=edge.get('from'),edge.get('to');kind=edge.get('kind')
        if a not in nodes or b not in nodes or a==b or kind not in ('sidewalk','crossing','shared_lot','steps'):raise ValueError('Invalid pedestrian edge')
        pair=tuple(sorted((a,b)))
        if pair in seen:raise ValueError('Duplicate pedestrian edge')
        seen.add(pair)
        if obstacles.hits(nodes[a],nodes[b]):raise ValueError('Pedestrian edge crosses a building or parking bay')
        if road.hits(nodes[a],nodes[b]) and kind!='crossing':raise ValueError('Road crossing outside a configured crossing link')
        if kind=='crossing' and not edge.get('crossing_id'):raise ValueError('Crossing needs a stable ID')
        if kind=='crossing' and data.get('crossings') is not None:
            definition=data['crossings'].get(edge['crossing_id'])
            if not definition or not any((math.dist(nodes[a],p)<1e-4 and math.dist(nodes[b],q)<1e-4) or (math.dist(nodes[a],q)<1e-4 and math.dist(nodes[b],p)<1e-4) for p,q in zip(definition['points'],definition['points'][1:])):raise ValueError('Road edge is outside its declared crossing geometry')
    access=data.get('space_access',{});dest=data.get('destination_access',{})
    if set(access)!=set(slots) or set(dest)!=doors:raise ValueError('Pedestrian access maps must cover all spaces and destinations; use null for disconnected locations')
    for sid,item in access.items():
        if item is None:continue
        if item.get('node') not in nodes or not isinstance(item.get('points'),list) or len(item['points'])<2:raise ValueError('Invalid bay walking connector')
        pts=item['points'];s=slots[sid]
        if math.dist(pts[0],[s['local_x_m'],s['local_y_m']])>1e-4 or math.dist(pts[-1],nodes[item['node']])>1e-4:raise ValueError('Walking connector endpoints do not match bay and graph')
        for a,b in zip(pts,pts[1:]):
            if obstacles.hits(a,b,ignore=sid):raise ValueError('Bay connector crosses another bay or building')
            # Explicit own-bay egress is allowed; road crossing connectors are not.
            from panda_abm.environment.pedestrian_geometry import segment_hits_polygon
            own=bay_polygon(s)
            from panda_abm.environment.pedestrian_geometry import inside,point_segment
            # An on-street bay may step across its own parking lane to the curb (<=3 m).
            curb=item.get('source')=='curb_step_parking_lane'
            for i in range(1,max(2,math.ceil(math.dist(a,b)/.1))):
                t=i/max(2,math.ceil(math.dist(a,b)/.1));p=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])]
                if not inside(p,own) and road.hits(p,p):
                    if curb and min(point_segment(p,u,v) for u,v in zip(own,own[1:]+own[:1]))<=3.:continue
                    raise ValueError('Bay connector crosses a road')
    for did,n in dest.items():
        if n is None:continue
        if n not in nodes:raise ValueError('Unknown pedestrian destination node')
        door=next(d for d in raw['walmart_doors'] if d['id']==did)
        if math.dist(nodes[n],[door['local_x_m'],door['local_y_m']])>1e-4:raise ValueError('Destination must be at its walking-network entrance')
    PedestrianNetwork(data)
    if len(_VALIDATED)>8:_VALIDATED.clear()
    _VALIDATED.add(digest)
