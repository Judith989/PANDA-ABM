"""Connected, estimated aisle topology inferred from parking-row geometry.

Main modules form parallel aisles joined at their ends. Walmart O/P/Q are
side-of-building corridors, connected through the front road, never across the
building. This is an explicit approximation, not a surveyed road network.
"""
from __future__ import annotations

from collections import defaultdict
from collections import OrderedDict
import math
import networkx as nx
import numpy as np


class AisleNetwork:
    def __init__(self, facility):
        self.graph = nx.Graph()
        self.positions = {}
        self.space_nodes = {}
        self.patrol_nodes = []
        self.aisle_nodes = {}
        self.aisle_spaces = {}
        self.space_aisle = {}
        self._point_nodes = {}
        groups = defaultdict(list)
        for space in facility.spaces:
            groups[space.module_id].append(space)
        main = {k:v for k,v in groups.items() if facility.synthetic or k not in {'Parking_Module_O','Parking_Module_P','Parking_Module_Q'}}
        ordered = sorted(main.values(), key=lambda v: np.mean([s.x_m for s in v]))
        if not ordered:
            raise ValueError('Navigation requires at least one parking space')
        centers = [float(np.mean([s.x_m for s in v])) for v in ordered]
        lanes = [min(s.x_m for s in ordered[0])-6.]
        lanes += [(a+b)/2 for a,b in zip(centers,centers[1:])]
        lanes += [max(s.x_m for s in ordered[-1])+6.]
        front_y = min(s.y_m for v in ordered for s in v)-8.
        lines = []
        for i,x in enumerate(lanes):
            adjacent = ordered[max(0,i-1):min(len(ordered),i+1)]
            north_y = min(max(s.y_m for s in v) for v in adjacent)+8.
            lines.append((x,front_y,north_y))
        assignments = defaultdict(list)
        for v in ordered:
            for s in v:
                i = min(range(len(lines)),key=lambda j: abs(s.x_m-lines[j][0])+max(0,s.y_m-lines[j][2]))
                assignments[i].append(s)
        south=[];north=[]
        for i,(x,y0,y1) in enumerate(lines):
            a,b=self._lane(x,y0,y1,assignments[i]);south.append(a);north.append(b)
        for ends in (south,north):
            for a,b in zip(ends,ends[1:]): self._edge(a,b)
        # Side corridors connect via the front cross-aisle.
        for side,keys in [('west',['Parking_Module_O']),('east',['Parking_Module_P','Parking_Module_Q'])]:
            spaces=[s for k in keys for s in groups.get(k,[])] if not facility.synthetic else []
            if not spaces:continue
            x=(min(s.x_m for s in spaces)-7.) if side=='west' else (max(s.x_m for s in spaces)+7.)
            a,b=self._lane(x,min(s.y_m for s in spaces)-5.,front_y,spaces)
            self._edge(b,south[0] if side=='west' else south[-1])
        self.exit_nodes=[]
        for point in facility.entry_points+facility.exit_points:
            node=self._node(point)
            if self.graph.degree(node)==0:
                junction=min(self.patrol_nodes,key=lambda n: math.dist(point,self.positions[n]))
                self._edge(node,junction)
            self.exit_nodes.append(node)
        if not nx.is_connected(self.graph):raise ValueError('Disconnected aisle network')
        self._edges=list(self.graph.edges())
        self._starts=np.array([self.positions[a] for a,b in self._edges])
        self._vectors=np.array([self.positions[b] for a,b in self._edges])-self._starts
        self._squared=(self._vectors*self._vectors).sum(axis=1)
        self._path_cache=OrderedDict()

    def _node(self, point):
        point=tuple(float(v) for v in point);key=tuple(round(v,8) for v in point)
        if key not in self._point_nodes:
            node=len(self.positions);self._point_nodes[key]=node;self.positions[node]=point;self.graph.add_node(node)
        return self._point_nodes[key]

    def _edge(self,a,b):
        if a!=b:self.graph.add_edge(a,b,weight=math.dist(self.positions[a],self.positions[b]))

    def _lane(self,x,y0,y1,spaces):
        # Split at every stall projection: every stall is reached by its own spur.
        ys=sorted({float(y0),float(y1)}|{float(np.clip(s.y_m,y0,y1)) for s in spaces})
        nodes=[self._node((x,y)) for y in ys]
        for a,b in zip(nodes,nodes[1:]):self._edge(a,b)
        for s in spaces:
            road=self._node((x,float(np.clip(s.y_m,y0,y1))))
            stall=self._node((s.x_m,s.y_m));self._edge(road,stall);self.space_nodes[s.space_id]=stall
        self.patrol_nodes.extend([nodes[0],nodes[-1]])
        aisle_id=f'aisle_{len(self.aisle_nodes):02d}'
        self.aisle_nodes[aisle_id]=(nodes[0],nodes[-1])
        self.aisle_spaces[aisle_id]=tuple(s.space_id for s in spaces)
        for s in spaces:self.space_aisle[s.space_id]=aisle_id
        return nodes[0],nodes[-1]

    def _anchors(self,position):
        key=tuple(round(v,8) for v in position)
        if key in self._point_nodes:return [(self._point_nodes[key],0.,tuple(position))]
        offset=np.asarray(position)-self._starts
        t=np.clip((offset*self._vectors).sum(axis=1)/self._squared,0.,1.)
        feet=self._starts+t[:,None]*self._vectors
        squared=((feet-position)**2).sum(axis=1)
        i=int(np.argmin(squared));a,b=self._edges[i];foot=tuple(feet[i]);distance=float(np.sqrt(squared[i]))
        return [(n,distance+math.dist(foot,self.positions[n]),foot) for n in (a,b)]

    def distances(self,position,targets=None):
        anchors=self._anchors(position)
        # Multi-source Dijkstra with nonzero source costs, without mutating graph.
        import heapq
        dist={n:cost for n,cost,_ in anchors};queue=[(cost,n) for n,cost,_ in anchors];heapq.heapify(queue)
        remaining=set(targets) if targets is not None else None
        while queue:
            cost,n=heapq.heappop(queue)
            if cost>dist[n]+1e-9:continue
            if remaining is not None:
                remaining.discard(n)
                if not remaining:break
            for neighbor,edge in self.graph[n].items():
                new=cost+edge['weight']
                if new<dist.get(neighbor,float('inf')):
                    dist[neighbor]=new;heapq.heappush(queue,(new,neighbor))
        return dist

    def route(self,position,node):
        if node not in self._path_cache:
            self._path_cache[node]=nx.single_source_dijkstra(self.graph,node)
            if len(self._path_cache)>64:self._path_cache.popitem(last=False)
        self._path_cache.move_to_end(node)
        lengths,paths=self._path_cache[node]
        anchor,_,foot=min(self._anchors(position),key=lambda a:a[1]+lengths[a[0]])
        return [foot]+[self.positions[n] for n in reversed(paths[anchor])]

    def next_patrol(self,position,visits):
        distances=self.distances(position)
        return min(self.patrol_nodes,key=lambda n:(visits.get(n,0),distances[n],n))
