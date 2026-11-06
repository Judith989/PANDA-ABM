"""Build source-labelled walking graphs for Walmart variants and the fictional transfer.

OSM supplies mapped footprints and pedestrian paths. Internal parking-lot gaps are
explicit estimated shared-space connections, never presented as mapped sidewalks.
"""
from pathlib import Path
import json,math,hashlib,xml.etree.ElementTree as ET
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
OUT=ROOT/'research/walmart_pedestrians_20261105'

def build(raw,name,osm_path=None):
 from shapely.geometry import Polygon,LineString,Point,box,MultiPoint
 from shapely.ops import unary_union
 from shapely import contains_xy
 from scipy.spatial import cKDTree
 import numpy as np
 import networkx as nx
 from panda_abm.environment.pedestrian_geometry import bay_polygon
 from panda_abm.environment.pedestrian_navigation import PedestrianNetwork
 from panda_abm.twin.environments import validate_environment
 buildings=[];mapped=[];excluded=[];public_roads=[]
 meta=raw['meta'];lat,lon=meta['ref_lat'],meta['ref_lon']
 local=lambda xy:((xy[0]-lon)*111000*math.cos(math.radians(lat)),(xy[1]-lat)*111000)
 points=[[s['local_x_m'],s['local_y_m']] for s in raw['slots']]+[[d['local_x_m'],d['local_y_m']] for d in raw['walmart_doors']]
 scope=MultiPoint(points).convex_hull.buffer(14,join_style=2)
 if osm_path:
  root=ET.parse(osm_path).getroot();coords={n.get('id'):(float(n.get('lon')),float(n.get('lat'))) for n in root.findall('node')}
  for w in root.findall('way'):
   t={x.get('k'):x.get('v') for x in w.findall('tag')};pp=[local(coords[x.get('ref')]) for x in w.findall('nd') if x.get('ref') in coords]
   if len(pp)<2:continue
   line=LineString(pp)
   if not line.intersects(scope):continue
   if t.get('highway') in ('motorway','trunk','primary','secondary','tertiary','residential','unclassified'):
    public_roads.append(line.buffer(5 if t['highway']=='residential' else 8,cap_style=2))
   if t.get('building') and t['building']!='no' and len(pp)>3 and pp[0]==pp[-1]:
    poly=Polygon(pp).buffer(0)
    if poly.geom_type=='Polygon':buildings.append(dict(id='osm_'+w.get('id'),footprint_m=[list(p) for p in poly.exterior.coords[:-1]],source='OpenStreetMap',osm_tags=t))
   if t.get('highway') in ('footway','path','pedestrian','steps'):
    if t.get('foot') in ('no','private') or (t.get('access') in ('no','private') and t.get('foot') not in ('yes','designated','permissive')) or t.get('highway')=='steps' or t.get('layer','0')!='0':excluded.append(w.get('id'));continue
    mapped.append(dict(id=w.get('id'),points=pp,tags=t))
 raw['buildings']=buildings
 building_union=unary_union([Polygon(b['footprint_m']).buffer(.2) for b in buildings])
 bays={s['id']:Polygon(bay_polygon(s)).buffer(.12,join_style=2) for s in raw['slots']}
 from shapely.strtree import STRtree
 bay_ids=list(bays);bay_geometries=list(bays.values());bay_tree=STRtree(bay_geometries)
 obstacles=unary_union([building_union,*bays.values()])
 mapped_union=unary_union([LineString(p['points']).buffer(1.2) for p in mapped])
 # Internal lot surfaces are estimated from the configured extent, not OSM footways.
 roads=unary_union(public_roads)
 free=scope.union(mapped_union.intersection(scope.buffer(8))).difference(obstacles).difference(roads)
 xmin,ymin,xmax,ymax=free.bounds;step=2.
 xs=np.arange(math.floor(xmin),math.ceil(xmax)+1,step);ys=np.arange(math.floor(ymin),math.ceil(ymax)+1,step)
 xx,yy=np.meshgrid(xs,ys);mask=contains_xy(free,xx,yy);nodes={};cells={}
 for j,i in zip(*np.where(mask)):
  k=f'p{len(nodes):05}';nodes[k]=[float(xs[i]),float(ys[j])];cells[i,j]=k
 if len(nodes)>49000:raise ValueError('Walking graph too large')
 edges=[]
 for (i,j),a in cells.items():
  for di,dj in ((1,0),(0,1),(1,1),(1,-1)):
   b=cells.get((i+di,j+dj))
   if b and free.covers(LineString([nodes[a],nodes[b]])):
    ism=mapped_union.covers(LineString([nodes[a],nodes[b]]))
    edges.append(dict(**{'from':a,'to':b},kind='sidewalk' if ism else 'shared_lot',source='osm_mapped_path' if ism else ('generated_synthetic_shared_space' if not osm_path else 'estimated_internal_shared_space_requires_review')))
 ids=list(nodes);tree=cKDTree([nodes[k] for k in ids]);access={};dest={};adjustments=[]
 for s in raw['slots']:
  p=[s['local_x_m'],s['local_y_m']];ds,ix=tree.query(p,k=min(100,len(ids)));candidates=[]
  for d,i in zip(np.atleast_1d(ds),np.atleast_1d(ix)):
   if d>12:continue
   k=ids[int(i)];line=LineString([p,nodes[k]])
   if line.intersects(building_union):continue
   if line.difference(Polygon(bay_polygon(s))).intersects(roads):continue
   # Query nearby bays only; own-bay egress is allowed.
   if any(bay_ids[int(idx)]!=s['id'] for idx in bay_tree.query(line,predicate='intersects')):continue
   candidates.append((float(d),k))
  if candidates:
   _,k=min(candidates);access[s['id']]=dict(node=k,points=[p,nodes[k]],source='estimated_obstacle_checked_bay_egress')
  else:access[s['id']]=None
 # Keep exact configured doors when free, otherwise explicitly record exterior snap.
 for door in raw['walmart_doors']:
  p=[door['local_x_m'],door['local_y_m']];ds,ix=tree.query(p,k=min(150,len(ids)));valid=[]
  for d,i in zip(np.atleast_1d(ds),np.atleast_1d(ix)):
   if d>15:continue
   k=ids[int(i)]
   if not obstacles.intersects(LineString([p,nodes[k]])):valid.append((float(d),k))
  if valid:
   _,k=min(valid);key='door_'+door['id'];nodes[key]=p;edges.append(dict(**{'from':key,'to':k},kind='shared_lot',source='estimated_entrance_connector'));dest[door['id']]=key
  else:
   dist,i=tree.query(p)
   if dist<=15:
    k=ids[int(i)];door['original_assumed_position_m']=p;door['local_x_m'],door['local_y_m']=nodes[k];door['entrance_status']='estimated_exterior_snap_requires_review';dest[door['id']]=k;adjustments.append(dict(destination=door['id'],from_m=p,to_m=nodes[k],distance_m=float(dist)))
   else:dest[door['id']]=None
 raw['pedestrian_road_areas']=[list(p.exterior.coords)[:-1] for p in public_roads if p.geom_type=='Polygon']
 raw['pedestrian_network']=dict(version=1,nodes=nodes,edges=edges,space_access=access,destination_access=dest,road_polygons=raw['pedestrian_road_areas'],crossings={},provenance=dict(osm_sha256=hashlib.sha256(osm_path.read_bytes()).hexdigest() if osm_path else None,osm_source='https://www.openstreetmap.org/api/0.6/map?bbox=-105.5445,41.2985,-105.5360,41.3055' if osm_path else None,attribution='OpenStreetMap contributors, ODbL' if osm_path else 'Generated fictional geometry; not OSM-mapped',grid_resolution_m=step,connector_policy='No straight-line fallback; disconnected spaces remain unavailable for that destination',internal_path_status='Estimated shared parking surface, not verified sidewalks or marked crossings',walking_safety='Shared-space vehicle/pedestrian separation; no invented mapped crossing claims',excluded_pedestrian_ways=excluded))
 nav=PedestrianNetwork(raw['pedestrian_network']);counts={did:sum(math.isfinite(nav.distance(s['id'],did)) for s in raw['slots'] if not s.get('is_unavailable') and not s.get('is_blocked')) for did in dest}
 for s in raw['slots']:s['walking_distance_to_destinations_m']={did:round(nav.distance(s['id'],did),3) if math.isfinite(nav.distance(s['id'],did)) else None for did in dest}
 report=dict(environment=name,nodes=len(nodes),edges=len(edges),mapped_pedestrian_ways=len(mapped),osm_buildings=len(buildings),reachable_usable_by_destination=counts,door_adjustments=adjustments,spaces_with_egress=sum(x is not None for x in access.values()))
 raw['pedestrian_network']['summary']=report;raw['meta']['walking_status']='OSM-derived footprints and mapped paths with estimated shared-lot connections' if osm_path else 'Explicit generated walking graph for fictional geometry'
 validated=validate_environment(dict(id=name,config=raw))['config']
 (OUT/(name+'_report.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.collections import LineCollection
 fig,ax=plt.subplots(figsize=(12,12))
 for b in buildings:ax.fill(*zip(*b['footprint_m']),color='#a59b88')
 for kind,color in [('shared_lot','#9ac4a3'),('sidewalk','#007d99')]:ax.add_collection(LineCollection([[nodes[e['from']],nodes[e['to']]] for e in edges if e['kind']==kind],colors=color,linewidths=.4,label=kind.replace('_',' ')))
 for d in raw['walmart_doors']:ax.scatter(d['local_x_m'],d['local_y_m'],c='red',marker='s');ax.annotate(d['id'],(d['local_x_m'],d['local_y_m']),fontweight='bold')
 ax.autoscale();ax.set_aspect('equal');ax.set_xlabel('East (m)',fontweight='bold');ax.set_ylabel('North (m)',fontweight='bold');ax.legend();fig.savefig(OUT/(name+'_overlay.png'),dpi=180,bbox_inches='tight');plt.close(fig)
 print(json.dumps(report),flush=True)
 return validated

def main():
 from panda_abm.twin.environments import export_network,synthetic_environment
 from panda_abm.environment import load_facility_from_lot_config
 OUT.mkdir(parents=True,exist_ok=True)
 # Build synthetic before modifying the source configuration.
 synthetic=synthetic_environment()['config']
 for filename,name in [('lot_config.json','walmart_original'),('lot_config.satellite_estimated.json','walmart_satellite')]:
  path=ROOT/'data'/filename;raw=json.loads(path.read_text(encoding='utf8'))
  backup=OUT/('before_'+filename)
  if not backup.exists():backup.write_bytes(path.read_bytes())
  if 'aisle_network' not in raw:raw['aisle_network']=export_network(load_facility_from_lot_config(path))
  result=build(raw,name,OUT/'osm_network.osm');path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
 result=build(synthetic,'synthetic');(ROOT/'data/lot_config.synthetic.json').write_text(json.dumps(result,separators=(',',':'))+'\n',encoding='utf8')

if __name__=='__main__':main()
