"""Extract OSM footways and build an obstacle-checked downtown walking graph.
Shapely is a build-time dependency only. Runtime routing uses NetworkX.
"""
from pathlib import Path
import math,json,hashlib,xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
OUT=ROOT/'research/downtown_pedestrians_20261105'

def main():
 global OUT
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=OUT)
 OUT=parser.parse_args().output
 from shapely.geometry import Polygon,LineString,Point,box
 from shapely.ops import unary_union
 from shapely import contains_xy
 from scipy.spatial import cKDTree
 import networkx as nx
 from panda_abm.environment.pedestrian_geometry import bay_polygon
 OUT.mkdir(parents=True,exist_ok=True)
 path=ROOT/'data/lot_config.downtown_laramie.json';raw=json.loads(path.read_text(encoding='utf8'))
 if not (OUT/'before_config.json').exists():(OUT/'before_config.json').write_text(json.dumps(raw,indent=2),encoding='utf8')
 meta=raw['meta'];lat,lon=meta['ref_lat'],meta['ref_lon'];local=lambda xy:((xy[0]-lon)*111000*math.cos(math.radians(lat)),(xy[1]-lat)*111000)
 osm_path=ROOT/'research/downtown_review/20261105/osm_network.osm';root=ET.parse(osm_path).getroot();coords={n.get('id'):(float(n.get('lon')),float(n.get('lat'))) for n in root.findall('node')}
 tags=lambda element:{t.get('k'):t.get('v') for t in element.findall('tag')}
 info=json.loads((ROOT/'research/downtown_review/20261105/imagery.json').read_text());n=2**info['zoom']
 def pixel(x,y):
  ll=((info['tile_x0']+x/256)/n*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*(info['tile_y0']+y/256)/n)))))
  return local(ll)
 grid=[[pixel(*p) for p in row] for row in [[(390,135),(860,155),(1337,180)],[(357,610),(825,635),(1310,662)],[(322,1090),(775,1110),(1270,1140)]]]
 scope=box(-145,-133,143,141)
 buildings=[Polygon(b['footprint_m']).buffer(.30,join_style=2) for b in raw['buildings']]
 bays={s['id']:Polygon(bay_polygon(dict(s,length_m=max(s.get('length_m',4.9),5.45),width_m=max(s.get('width_m',2.06),2.05)))).buffer(.30,join_style=2) for s in raw['slots']}
 building_union=unary_union(buildings);obstacles=unary_union(buildings+list(bays.values()))
 road_polys=[];sidewalks=[]
 # Estimated sidewalk ribbons supplement mapped paths, with explicit provenance.
 for i in range(3):
  width=[5.,8.,11.][i];offset=[8.,12.,15.][i]
  for j in range(2):
   a,b=grid[j][i],grid[j+1][i];road_polys.append(LineString([a,b]).buffer(width,cap_style=2))
   for sign in ([1] if i==0 else [-1,1]):
    # East/west offsets, with width sufficient for the draft image registration.
    sidewalk=LineString([(a[0]+sign*offset,a[1]),(b[0]+sign*offset,b[1])]);sidewalks.append(sidewalk.buffer(2.5,cap_style=3))
 for j in range(3):
  for i in range(2):
   a,b=grid[j][i],grid[j][i+1];road_polys.append(LineString([a,b]).buffer(7.5 if j==0 else 8.5,cap_style=2))
   for sign in [-1,1]:sidewalks.append(LineString([(a[0],a[1]+sign*12),(b[0],b[1]+sign*12)]).buffer(2.5,cap_style=3))
 for aid in ('lot_north','lot_south'):
  aa,bb=raw['aisle_network']['aisles'][aid];road_polys.append(LineString([raw['aisle_network']['nodes'][aa],raw['aisle_network']['nodes'][bb]]).buffer(2.5,cap_style=2))
 # Include the corrected driveways and connectors, not only the schematic
 # street grid. Walkers must not follow a corridor occupied by a driving lane.
 # 2.7 m covers the 1.2-m lane offset, vehicle half-width and pedestrian margin.
 vehicle_nodes=raw['aisle_network']['nodes']
 for a,b in raw['aisle_network']['edges']:
  road_polys.append(LineString([vehicle_nodes[a],vehicle_nodes[b]]).buffer(2.7,cap_style=2))
 roads=unary_union(road_polys)
 accepted=[];excluded=[];crossings=[];osm_corridors=[];restricted=[];crossing_definitions={}
 for way in root.findall('way'):
  t=tags(way)
  if t.get('highway') not in ('footway','path','pedestrian','steps'):continue
  points=[local(coords[v.get('ref')]) for v in way.findall('nd')];line=LineString(points)
  if not line.intersects(scope):excluded.append(dict(id=way.get('id'),reason='outside_scope'));continue
  if t.get('foot') in ('no','private') or (t.get('access') in ('no','private') and t.get('foot') not in ('yes','designated','permissive')):excluded.append(dict(id=way.get('id'),reason='pedestrian_access_restricted'));restricted.append(line.buffer(1.5));continue
  if t.get('layer','0')!='0' or t.get('highway')=='steps':excluded.append(dict(id=way.get('id'),reason='grade_or_stairs_not_connected_in_this_flat_accessible_draft'));continue
  accepted.append(dict(id=way.get('id'),tags=t,points_m=points))
  if t.get('footway')=='crossing':crossings.append(dict(id='osm_'+way.get('id'),points=points,source='osm_mapped_crossing'))
  else:osm_corridors.append(line.buffer(1.,cap_style=3))
 # Additional lot walking space is estimated from imagery, never through another bay.
 lot=Polygon([pixel(*p) for p in [(366,735),(573,752),(551,1030),(340,1015)]]).buffer(0)
 for node in root.findall('node'):
  t=tags(node)
  if t.get('barrier') and (t.get('foot')=='no' or t.get('access') in ('no','private')):restricted.append(Point(local(coords[node.get('id')])).buffer(1.))
 free=unary_union(sidewalks+osm_corridors+[lot]).intersection(scope).difference(obstacles).difference(roads.buffer(.05)).difference(unary_union(restricted))
 xs=np.arange(-145,144,1.);ys=np.arange(-133,142,1.);xx,yy=np.meshgrid(xs,ys);mask=contains_xy(free,xx,yy)
 nodes={};cells={}
 for j,i in zip(*np.where(mask)):
  key=f'p{len(nodes):05}';nodes[key]=[round(float(xs[i]),4),round(float(ys[j]),4)];cells[(i,j)]=key
 tree=cKDTree(list(nodes.values()));node_ids=list(nodes);edges=[];seen=set()
 def add(a,b,kind,source,crossing=None):
  pair=tuple(sorted((a,b)))
  if a==b or pair in seen:return
  seen.add(pair);edge=dict(from_=a,to=b,kind=kind,source=source);edge['from']=edge.pop('from_')
  if crossing:edge['crossing_id']=crossing
  edges.append(edge)
 for (i,j),a in cells.items():
  for di,dj in [(1,0),(0,1),(1,1),(1,-1)]:
   b=cells.get((i+di,j+dj))
   if b and free.covers(LineString([nodes[a],nodes[b]])):
    mid=Point((np.asarray(nodes[a])+nodes[b])/2)
    mapped=any(p.covers(mid) for p in osm_corridors)
    add(a,b,'shared_lot' if lot.covers(mid) else 'sidewalk','osm_mapped_path' if mapped else 'image_estimated_connection')
 # Image-based crossing hypotheses at the visible block corners. Marked separately.
 for j in range(3):
  for i in range(3):
   x,y=grid[j][i];off=[8.,12.,15.][i]
   if i>0:
    for sign in [-1,1]:crossings.append(dict(id=f'image_{j}_{i}_ew_{sign}',points=[(x-off,y+sign*12),(x+off,y+sign*12)],source='image_estimated_crossing_requires_review'))
   for sign in ([1] if i==0 else [-1,1]):crossings.append(dict(id=f'image_{j}_{i}_ns_{sign}',points=[(x+sign*off,y-12),(x+sign*off,y+12)],source='image_estimated_crossing_requires_review'))
 for name,y in [('north',797),('south',932)]:
  for side,x in [('west',385),('east',558)]:crossings.append(dict(id='lot_'+name+'_'+side,points=[pixel(x,y-17),pixel(x,y+17)],source='image_estimated_lot_crossing_requires_review'))
 crossing_report=[]
 for crossing in crossings:
  pts=crossing['points'];ends=[]
  for endpoint in (pts[0],pts[-1]):
   ds,ids=tree.query(endpoint,k=min(25,len(node_ids)));valid=[]
   for d,idx in zip(np.atleast_1d(ds),np.atleast_1d(ids)):
    if d>9:continue
    q=nodes[node_ids[int(idx)]];line=LineString([endpoint,q])
    if not line.intersects(obstacles):valid.append((float(d),node_ids[int(idx)]))
   ends.append(min(valid)[1] if valid else None)
  if not all(ends) or ends[0]==ends[1]:crossing_report.append(dict(id=crossing['id'],accepted=False,reason='missing_clear_sidewalk_end'));continue
  route=[nodes[ends[0]],*pts,nodes[ends[1]]];line=LineString(route)
  if line.intersects(obstacles) or (restricted and line.intersects(unary_union(restricted))):crossing_report.append(dict(id=crossing['id'],accepted=False,reason='obstacle_conflict'));continue
  if any(line.hausdorff_distance(LineString(c['points']))<2 for c in crossing_definitions.values()):crossing_report.append(dict(id=crossing['id'],accepted=False,reason='duplicate_crossing_geometry'));continue
  chain=[ends[0]]
  for p in pts:
   if math.dist(p,nodes[chain[-1]])<1e-4:continue
   key=f'c{len(nodes):05}';nodes[key]=[round(float(v),4) for v in p];chain.append(key)
  chain.append(ends[1])
  crossing_definitions[crossing['id']]=dict(points=[nodes[k] for k in chain],source=crossing['source'])
  for a,b in zip(chain,chain[1:]):add(a,b,'crossing',crossing['source'],crossing['id'])
  crossing_report.append(dict(id=crossing['id'],accepted=True,source=crossing['source']))
 # Tree remains limited to obstacle-free sidewalk/lot nodes, never a road crossing node.
 access={};rejected=[]
 for slot in raw['slots']:
  sid=slot['id'];p=[slot['local_x_m'],slot['local_y_m']];ds,ids=tree.query(p,k=min(60,len(node_ids)));options=[]
  for d,idx in zip(np.atleast_1d(ds),np.atleast_1d(ids)):
   if d>12:continue
   key=node_ids[int(idx)];q=nodes[key];line=LineString([p,q])
   if line.intersects(building_union):continue
   if any(line.intersects(poly) for other,poly in bays.items() if other!=sid):continue
   if line.difference(Polygon(bay_polygon(slot))).intersects(roads):continue
   options.append((float(d),key))
  if options:
   _,key=min(options);access[sid]=dict(node=key,points=[p,nodes[key]],source='estimated_bay_egress_obstacle_checked')
  else:access[sid]=None;rejected.append(sid)
 graph=nx.Graph();graph.add_nodes_from(node_ids);graph.add_edges_from((e['from'],e['to']) for e in edges)
 main_component=max(nx.connected_components(graph),key=len)
 major_ids=[k for k in node_ids if k in main_component];major_tree=cKDTree([nodes[k] for k in major_ids])
 destinations={};dest_report=[]
 for d in raw['destinations']:
  old=d.get('original_assumed_position_m',[d['local_x_m'],d['local_y_m']]);dist,idx=major_tree.query(old);key=major_ids[int(idx)]
  if dist>30:destinations[d['id']]=None;dest_report.append(dict(id=d['id'],connected=False));continue
  d.setdefault('original_assumed_position_m',old);d['local_x_m'],d['local_y_m']=nodes[key]
  d['entrance_status']='estimated_exterior_access_point_not_a_verified_door';d['walking_snap_m']=round(float(dist),3);destinations[d['id']]=key
  dest_report.append(dict(id=d['id'],connected=True,snap_m=float(dist),source=d['entrance_status']))
 raw['walmart_doors']=json.loads(json.dumps(raw['destinations']))
 raw['pedestrian_road_areas']=[list(p.exterior.coords)[:-1] for p in road_polys]
 raw['pedestrian_network']=dict(version=1,nodes=nodes,edges=edges,space_access=access,destination_access=destinations,road_polygons=raw['pedestrian_road_areas'],crossings=crossing_definitions,provenance=dict(osm_sha256=hashlib.sha256(osm_path.read_bytes()).hexdigest(),grid_resolution_m=1.0,building_clearance_m=.30,bay_clearance_m=.30,maximum_vehicle_envelope_m=[5.45,2.05],connector_policy='No route if disconnected; never straight-line fallback',sidewalk_gap_policy='Mapped paths supplemented by image-estimated ribbons; source retained per edge',crossing_policy='Gap acceptance and vehicle yielding during occupied crossing',destination_policy='Estimated exterior access points; actual doors require review'))
 raw['meta']['walking_status']='Obstacle-checked pedestrian graph; estimated connections and entrances; dynamic crossing waits'
 # Validate against actual raw footprints, bays and declared crossing links.
 from panda_abm.twin.environments import validate_environment
 (OUT/'osm_pedestrian_features.json').write_text(json.dumps(dict(accepted=accepted,excluded=excluded,crossings=crossing_report),indent=2),encoding='utf8')
 from panda_abm.environment.pedestrian_navigation import PedestrianNetwork
 nav=PedestrianNetwork(raw['pedestrian_network']);counts={did:sum(math.isfinite(nav.distance(s['id'],did)) for s in raw['slots']) for did in destinations}
 report=dict(nodes=len(nodes),edges=len(edges),mapped_pedestrian_ways_retained=len(accepted),crossings_accepted=sum(c['accepted'] for c in crossing_report),spaces_with_egress=len(access)-len(rejected),disconnected_space_ids=rejected,destination_connections=dest_report,reachable_spaces_by_destination=counts,capacity=len(raw['slots']),source='OSM + explicitly estimated imagery connections; not surveyed')
 for slot in raw['slots']:
  slot['walking_distance_to_destinations_m']={did:round(nav.distance(slot['id'],did),3) if math.isfinite(nav.distance(slot['id'],did)) else None for did in destinations}
 raw['pedestrian_network']['summary']=dict(spaces_with_egress=len(access)-len(rejected),reachable_spaces_by_destination=counts)
 env=validate_environment(dict(id='downtown_laramie',config=raw))
 path.write_text(json.dumps(env['config'],indent=2)+'\n',encoding='utf8')
 (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.collections import LineCollection
 fig,ax=plt.subplots(figsize=(12,12))
 for b in raw['buildings']:ax.fill(*zip(*b['footprint_m']),color='#aaa18b',alpha=.8)
 for kind,color in [('sidewalk','#008b9c'),('shared_lot','#55a85b'),('crossing','#d36a00')]:
  lines=[[nodes[e['from']],nodes[e['to']]] for e in edges if e['kind']==kind];ax.add_collection(LineCollection(lines,colors=color,linewidths=.7,label=kind.replace('_',' ')))
 for d in raw['destinations']:ax.text(d['local_x_m'],d['local_y_m'],d['id'][-2:],fontsize=12,fontweight='bold',bbox=dict(facecolor='white',edgecolor='black',pad=1))
 ax.set_aspect('equal');ax.autoscale();ax.legend();ax.set_xlabel('East (m)',fontweight='bold');ax.set_ylabel('North (m)',fontweight='bold');fig.tight_layout();fig.savefig(OUT/'pedestrian_network.png',dpi=200);plt.close(fig)
 print(json.dumps(report))
if __name__=='__main__':main()
