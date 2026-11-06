"""Repair estimated shared-road connectors that cut through configured obstacles."""
from pathlib import Path
import json,math,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 from shapely.geometry import Polygon,LineString
 from shapely.ops import unary_union
 from shapely.strtree import STRtree
 from panda_abm.environment.pedestrian_geometry import bay_polygon
 out=ROOT/'research/vehicle_clearance_20261105';out.mkdir(exist_ok=True)
 for filename in ('lot_config.json','lot_config.satellite_estimated.json','lot_config.downtown_laramie.json','lot_config.synthetic.json'):
  path=ROOT/'data'/filename;raw=json.loads(path.read_text(encoding='utf8'));net=raw['aisle_network'];nodes=net['nodes']
  backup=out/('before_'+filename)
  if not backup.exists():backup.write_bytes(path.read_bytes())
  slots=raw['slots'];bay_points={(round(s['local_x_m'],7),round(s['local_y_m'],7)) for s in slots}
  bay_obstacles=[Polygon(bay_polygon(dict(s,length_m=max(s.get('length_m',4.9),5.45),width_m=max(s.get('width_m',2.06),2.02)))).buffer(2.3,join_style=2) for s in slots]
  buildings=[Polygon(b['footprint_m']).buffer(2.3,join_style=2) for b in raw.get('buildings',[])]
  obstacles=bay_obstacles+buildings;tree=STRtree(obstacles)
  clear=lambda p,q:not len(tree.query(LineString([p,q]),predicate='intersects'))
  xmin=min(s['local_x_m'] for s in slots)-12;xmax=max(s['local_x_m'] for s in slots)+12;ymin=min(s['local_y_m'] for s in slots)-12;ymax=max(s['local_y_m'] for s in slots)+12
  edges=[];changes=[];unresolved=[]
  for a,b in net['edges']:
   p,q=nodes[a],nodes[b]
   if tuple(round(v,7) for v in p) in bay_points or tuple(round(v,7) for v in q) in bay_points or clear(p,q):edges.append([a,b]);continue
   candidates=[]
   for y in (ymax,ymin,max(p[1],q[1])+10,min(p[1],q[1])-10):candidates.append([p,[p[0],y],[q[0],y],q])
   for x in (xmin,xmax,min(p[0],q[0])-10,max(p[0],q[0])+10):candidates.append([p,[x,p[1]],[x,q[1]],q])
   candidates=[c for c in candidates if all(math.dist(x,y)<1e-8 or clear(x,y) for x,y in zip(c,c[1:]))]
   if not candidates:edges.append([a,b]);unresolved.append([a,b]);continue
   route=min(candidates,key=lambda c:sum(math.dist(x,y) for x,y in zip(c,c[1:])))
   chain=[a]
   for point in route[1:-1]:
    if math.dist(nodes[chain[-1]],point)<1e-8:continue
    k='clearance_'+str(len(nodes));nodes[k]=point;chain.append(k)
   if math.dist(nodes[chain[-1]],q)<1e-8:chain[-1]=b
   else:chain.append(b)
   edges.extend([x,y] for x,y in zip(chain,chain[1:]) if x!=y)
   changes.append(dict(original=[a,b],route=route,source='estimated_obstacle_avoiding_connector_requires_review'))
  # Avoid duplicate edges while retaining directed counterparts where configured.
  seen=set();net['edges']=[]
  for a,b in edges:
   key=(a,b) if net.get('directed') else tuple(sorted((a,b)))
   if key not in seen:seen.add(key);net['edges'].append([a,b])
  net['clearance_repairs']=changes
  report=dict(file=filename,repaired=len(changes),unresolved=unresolved,estimated_not_surveyed=True)
  (out/(filename+'.report.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
  path.write_text(json.dumps(raw,separators=(',',':'))+'\n',encoding='utf8');print(report,flush=True)

if __name__=='__main__':main()
