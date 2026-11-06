"""Align bay-entry spurs to bay headings; split the existing aisle at the approach."""
from pathlib import Path
import sys,json,math
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 from shapely.geometry import LineString,Polygon
 from shapely.strtree import STRtree
 from panda_abm.environment.pedestrian_geometry import bay_polygon
 from panda_abm.core.traffic import crossing
 out=ROOT/'research/vehicle_clearance_20261105';out.mkdir(exist_ok=True)
 for filename in (sys.argv[1:] or ('lot_config.json','lot_config.satellite_estimated.json','lot_config.downtown_laramie.json','lot_config.synthetic.json')):
  path=ROOT/'data'/filename;raw=json.loads(path.read_text(encoding='utf8'));net=raw['aisle_network'];nodes=net['nodes'];slots=raw['slots']
  def fresh(prefix):
   index=len(nodes)
   while prefix+str(index) in nodes:index+=1
   return prefix+str(index)
  lookup={(round(v[0],7),round(v[1],7)):k for k,v in nodes.items()};stall={}
  for s in slots:
   point=(round(s['local_x_m'],7),round(s['local_y_m'],7));k=lookup.get(point)
   if k is None:k=fresh('bay_center_');nodes[k]=[s['local_x_m'],s['local_y_m']];lookup[point]=k
   stall[s['id']]=k
  stallset=set(stall.values())
  roads=[(a,b) for a,b in net['edges'] if a not in stallset and b not in stallset]
  polygons=[Polygon(bay_polygon(s)).buffer(.95,join_style=2) for s in slots];tree=STRtree(polygons);slotids=[s['id'] for s in slots]
  split={};spurs=[];changed=[];failed=[]
  for s in slots:
   sid=s['id'];p=[s['local_x_m'],s['local_y_m']];angle=math.radians(s.get('heading_deg',0))
   if s.get('heading_reference')=='clockwise_from_north':angle=math.pi/2-angle
   u=(math.cos(angle),math.sin(angle));options=[]
   for a,b in roads:
    q,r=nodes[a],nodes[b];l=math.dist(q,r)
    if not l:continue
    v=((r[0]-q[0])/l,(r[1]-q[1])/l);result=crossing(p,u,q,v)
    if result is None:continue
    t,d=result
    if not -.00001<=d<=l+.00001 or not .5<abs(t)<20:continue
    point=[p[0]+u[0]*t,p[1]+u[1]*t]
    if any(slotids[int(i)]!=sid for i in tree.query(LineString([p,point]),predicate='intersects')):continue
    options.append((abs(t),a,b,d/l,point))
   if not options:
    # Keep the existing connector if no safe heading-aligned intersection exists.
    old=net['space_access'][sid]['node']
    if old==stall[sid]:
     neighbors=[b if a==old else a for a,b in net['edges'] if (a==old or b==old) and a!=b]
     old=min(neighbors,key=lambda k:(k in stallset,math.dist(p,nodes[k]))) if neighbors else old
    net['space_access'][sid]['node']=old
    if old!=stall[sid]:spurs.append((old,stall[sid]))
    failed.append(sid);continue
   _,a,b,fraction,point=min(options)
   key=lookup.get((round(point[0],7),round(point[1],7)))
   if key is None:key=fresh('bay_approach_');nodes[key]=point;lookup[round(point[0],7),round(point[1],7)]=key
   split.setdefault((a,b),[]).append((fraction,key))
   if net.get('directed') and (b,a) in roads:split.setdefault((b,a),[]).append((1-fraction,key))
   net['space_access'][sid]['node']=key;spurs.append((key,stall[sid]));changed.append(sid)
  edges=[];chains={}
  for a,b in roads:
   chain=[a]+[k for _,k in sorted(split.get((a,b),[])) if k not in (a,b)]+[b]
   chains[a,b]=chain
   edges.extend((x,y) for x,y in zip(chain,chain[1:]) if x!=y)
  for a,b in spurs:
   edges.append((a,b))
   if net.get('directed'):edges.append((b,a))
  if net.get('turn_restrictions'):
   net['turn_restrictions']=[[chains.get((a,b),[a,b])[-2],b,chains.get((b,c),[b,c])[1]] for a,b,c in net['turn_restrictions']]
  seen=set();net['edges']=[]
  for a,b in edges:
   k=(a,b) if net.get('directed') else tuple(sorted((a,b)))
   if k not in seen:seen.add(k);net['edges'].append([a,b])
  report=dict(file=filename,aligned=len(changed),retained_existing=len(failed),retained_ids=failed,provenance='Generated heading-aligned approaches on the configured estimated aisle network; not surveyed turning radii')
  (out/(filename+'.approaches.json')).write_text(json.dumps(report,indent=2),encoding='utf8')
  path.write_text(json.dumps(raw,separators=(',',':'))+'\n',encoding='utf8');print(filename,len(changed),'aligned;',len(failed),'retained',flush=True)

if __name__=='__main__':main()
