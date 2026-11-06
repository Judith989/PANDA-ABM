"""Build a review-only downtown reconstruction from georeferenced image digitization.
No simulations are executed. Pixel row fits are estimates, not a surveyed inventory.
"""
from pathlib import Path
import math,json,hashlib,csv
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
OUT=ROOT/'research/downtown_review/20261105'
REF_LAT,REF_LON=41.311133611627,-105.594920909775

def main():
 from panda_abm.twin.environments import validate_environment
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Polygon
 from PIL import Image
 info=json.loads((OUT/'imagery.json').read_text(encoding='utf8'));n=2**info['zoom']
 def local(p):
  x,y=p;lon=(info['tile_x0']+x/256)/n*360-180;lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*(info['tile_y0']+y/256)/n))))
  return [(lon-REF_LON)*111000*math.cos(math.radians(REF_LAT)),(lat-REF_LAT)*111000]
 roads={};verts={}
 grid=[[(390,135),(860,155),(1337,180)],[(357,610),(825,635),(1310,662)],[(322,1090),(775,1110),(1270,1140)]]
 for j,row in enumerate(grid):
  for i,p in enumerate(row):verts[f'g{j}{i}']=p
 for j in range(3):
  for i in range(2):roads[f'cross_{j}_{i}']=(verts[f'g{j}{i}'],verts[f'g{j}{i+1}'])
 for i in range(3):
  for j in range(2):roads[f'street_{i}_{j}']=(verts[f'g{j}{i}'],verts[f'g{j+1}{i}'])
 # Two provisional lot circulation aisles, connected through assumed west curb cuts.
 roads['lot_north']=((343.4,797),(566,797));roads['lot_south']=((333.5,932),(548,932))
 slots=[]
 def row(a,b,count,group,kind,angle):
  for i in range(count):
   t=(i+.5)/count;p=(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]));x,y=local(p)
   slots.append(dict(id=f'DT{len(slots)+1:03}',module=group,local_x_m=round(x,4),local_y_m=round(y,4),source_pixel=list(p),heading_deg=angle,heading_reference='clockwise_from_north',length_m=5.1,width_m=2.5,parking_kind=kind,time_limit_minutes=120 if kind=='on_street' else None,rule_review_status='district_guidance_assumed_at_this_bay_not_sign_verified',is_accessible=False,is_reserved=False,is_unavailable=False,is_blocked=False,price_per_hour=0,type='regular',inventory_status='provisional_row_fit'))
 row((407,764),(557,786),11,'lot_row_1','off_street',150)
 row((403,819),(555,841),11,'lot_row_2','off_street',30)
 row((407,899),(543,923),10,'lot_row_3','off_street',150)
 row((397,944),(536,973),10,'lot_row_4','off_street',30)
 for a,b,c,g,angle in [((826,278),(810,521),16,'second_west_north',45),((881,290),(865,518),15,'second_east_north',225),((786,762),(765,1016),17,'second_west_south',45),((843,770),(824,1018),17,'second_east_south',225),((431,565),(563,578),9,'grand_north_west',150),((593,634),(749,644),10,'grand_south_west',30),((939,601),(1232,622),14,'grand_north_east',90),((895,668),(1038,680),10,'grand_south_east',30),((605,1050),(735,1065),9,'garfield_north_west',90),((852,1073),(1010,1085),10,'garfield_north_east',90),((595,1118),(709,1132),8,'garfield_south_west',30),((854,1137),(1004,1151),10,'garfield_south_east',30),((453,98),(587,107),9,'ivinson_north_west',150),((949,90),(1073,106),8,'ivinson_north_east',150),((622,165),(781,180),10,'ivinson_south_west',30),((951,193),(1089,207),9,'ivinson_south_east',30)]:row(a,b,c,g,'on_street',angle)
 for slot in slots:
  if slot['module'] in ['grand_south_west', 'grand_south_east', 'garfield_north_west', 'garfield_south_west', 'garfield_south_east', 'ivinson_south_west', 'ivinson_south_east']:slot['heading_deg']=150
 before=len(slots)
 row((369,235),(350,520),10,'first_east_north','on_street',4)
 row((346,795),(331,1010),8,'first_east_south','on_street',4)
 for slot in slots[before:]: slot['length_m']=6.0;slot['width_m']=2.3
 # Build a connected undirected network, splitting roads at all projected approaches.
 nodes={};edges=[];aisles={};space_access={};road_points=defaultdict(list)
 def node(p):
  xy=[round(v,4) for v in local(p)];key=','.join(map(str,xy))
  if key not in coord:coord[key]=f'n{len(nodes):04}';nodes[coord[key]]=xy
  return coord[key]
 coord={}
 def project(p,a,b):
  dx,dy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
  q=(a[0]+t*dx,a[1]+t*dy);return t,q,math.dist(p,q)
 for key,(a,b) in roads.items():road_points[key]=[(0,a),(1,b)];aisles[key]=[node(a),node(b)]
 # Attach lot entrances to the First Street segment at their matching point.
 for lot in ('lot_north','lot_south'):
  p=roads[lot][0];t,q,_=project(p,*roads['street_0_1']);road_points['street_0_1'].append((t,q));edges.append([node(q),node(p)])
 for s in slots:
  choices=[s['module'].startswith('lot_') and ('lot_north' if s['module'] in ('lot_row_1','lot_row_2') else 'lot_south')]
  key=choices[0] if choices[0] else min((k for k in roads if not k.startswith('lot_')),key=lambda k:project(s['source_pixel'],*roads[k])[2])
  t,q,_=project(s['source_pixel'],*roads[key]);road_points[key].append((t,q));space_access[s['id']]={'node':node(q),'aisle':key}
 for key,points in road_points.items():
  ordered=sorted(points,key=lambda p:p[0]);ids=list(dict.fromkeys(node(p) for _,p in ordered));edges.extend([a,b] for a,b in zip(ids,ids[1:]) if a!=b)
 entries=[];access_nodes={}
 for key in ('g00','g01','g02','g20','g21','g22'):
  x,y=local(verts[key]);pid='access_'+key;entries.append(dict(id=pid,name=pid.replace('_',' '),local_x_m=x,local_y_m=y));access_nodes[pid]=node(verts[key])
 dests=[]
 for i,(name,p) in enumerate([('Coal Creek Coffee',(425,694)),('Dukes Barber vicinity',(579,778)),('Bent and Rusty vicinity',(572,836)),('Green Oasis vicinity',(564,899)),('Altitude Chophouse',(759,1015)),('Born in a Barn',(420,217)),('Crowbar and Grill',(796,315)),('Sweet Melissa vicinity',(380,365))],1):
  x,y=local(p);dests.append(dict(id=f'destination_{i:02}',name=name,local_x_m=x,local_y_m=y,entrance_status='assumed_building_front_for_review'))
 raw=dict(schema_version=2,meta=dict(lot_name='Downtown Laramie — image-derived review draft',ref_lat=REF_LAT,ref_lon=REF_LON,synthetic=False,show_basemap=True,review_required=True,simulation_ready=False,destination_assignment='uniform over eight fixed destinations',rule_policy='Reject spaces when planned activity plus return walking exceeds time limit; no enforcement or overstay model.',geometry_status='Provisional georeferenced row digitization; not surveyed or independently counted',traffic_status='Undirected street centreline draft; signs, turns, signals, curb cuts and lane directions unverified',walking_status='Straight-line model only; pedestrian network not yet reconstructed',accessibility_status='No accessible designations inferred; inventory requires sign review',sources=['User-provided four overlapping screenshots','Esri World Imagery georeferenced review mosaic','https://laramiemainstreet.org/parking'],imagery_sha256=hashlib.sha256((OUT/'satellite.png').read_bytes()).hexdigest()),slots=slots,destinations=dests,entry_points=entries,exit_points=entries,aisle_network=dict(nodes=nodes,edges=edges,aisles=aisles,space_access=space_access,access_nodes=access_nodes))
 raw['meta']['inventory_complete']=False
 raw['meta']['geometry_audit_status']='Orientation convention corrected; off-street inventory incomplete and counts unverified'
 raw['unresolved_parking_areas']=[dict(id='off_street_north_pair',source_pixel_bounds=[390,745,563,802],issue='Possible paired/staggered arrangements; obscured markings'),dict(id='off_street_middle',source_pixel_bounds=[392,850,556,891],issue='Visible parking arrangements omitted by four-row fit'),dict(id='off_street_south',source_pixel_bounds=[385,970,554,1027],issue='Additional perimeter parking obscured by trees and obstructions')]
 raw['aisle_network']['segment_labels']={'street_0_0': {'road_name': 'South 1st Street', 'from': 'East Ivinson Avenue', 'to': 'East Grand Avenue', 'label': 'South 1st Street — East Ivinson Avenue to East Grand Avenue'}, 'street_0_1': {'road_name': 'South 1st Street', 'from': 'East Grand Avenue', 'to': 'East Garfield Street', 'label': 'South 1st Street — East Grand Avenue to East Garfield Street'}, 'street_1_0': {'road_name': 'South 2nd Street', 'from': 'East Ivinson Avenue', 'to': 'East Grand Avenue', 'label': 'South 2nd Street — East Ivinson Avenue to East Grand Avenue'}, 'street_1_1': {'road_name': 'South 2nd Street', 'from': 'East Grand Avenue', 'to': 'East Garfield Street', 'label': 'South 2nd Street — East Grand Avenue to East Garfield Street'}, 'street_2_0': {'road_name': 'South 3rd Street', 'from': 'East Ivinson Avenue', 'to': 'East Grand Avenue', 'label': 'South 3rd Street — East Ivinson Avenue to East Grand Avenue'}, 'street_2_1': {'road_name': 'South 3rd Street', 'from': 'East Grand Avenue', 'to': 'East Garfield Street', 'label': 'South 3rd Street — East Grand Avenue to East Garfield Street'}, 'cross_0_0': {'road_name': 'East Ivinson Avenue', 'from': 'South 1st Street', 'to': 'South 2nd Street', 'label': 'East Ivinson Avenue — South 1st Street to South 2nd Street'}, 'cross_0_1': {'road_name': 'East Ivinson Avenue', 'from': 'South 2nd Street', 'to': 'South 3rd Street', 'label': 'East Ivinson Avenue — South 2nd Street to South 3rd Street'}, 'cross_1_0': {'road_name': 'East Grand Avenue', 'from': 'South 1st Street', 'to': 'South 2nd Street', 'label': 'East Grand Avenue — South 1st Street to South 2nd Street'}, 'cross_1_1': {'road_name': 'East Grand Avenue', 'from': 'South 2nd Street', 'to': 'South 3rd Street', 'label': 'East Grand Avenue — South 2nd Street to South 3rd Street'}, 'cross_2_0': {'road_name': 'East Garfield Street', 'from': 'South 1st Street', 'to': 'South 2nd Street', 'label': 'East Garfield Street — South 1st Street to South 2nd Street'}, 'cross_2_1': {'road_name': 'East Garfield Street', 'from': 'South 2nd Street', 'to': 'South 3rd Street', 'label': 'East Garfield Street — South 2nd Street to South 3rd Street'}, 'lot_north': {'road_name': 'Off-street parking lot', 'from': 'South 1st Street', 'to': 'north circulation aisle', 'label': 'Off-street lot — north circulation aisle'}, 'lot_south': {'road_name': 'Off-street parking lot', 'from': 'South 1st Street', 'to': 'south circulation aisle', 'label': 'Off-street lot — south circulation aisle'}}
 env=validate_environment(dict(id='downtown_laramie_review',config=raw));OUT.mkdir(parents=True,exist_ok=True)
 (ROOT/'data/lot_config.downtown_laramie.review.json').write_text(json.dumps(env['config'],indent=2)+'\n',encoding='utf8')
 (OUT/'environment.review.json').write_text(json.dumps(env,indent=2)+'\n',encoding='utf8')
 for group in ('on_street','off_street'):
  (OUT/f'{group}.geojson').write_text(json.dumps(dict(type='FeatureCollection',features=[dict(type='Feature',geometry=dict(type='Point',coordinates=[s['lon'],s['lat']]),properties={k:s[k] for k in ('id','module','heading_deg','time_limit_minutes','inventory_status')}) for s in env['config']['slots'] if s['parking_kind']==group]),indent=2),encoding='utf8')
 plt.rcParams.update({'font.size':13,'font.weight':'bold','axes.labelweight':'bold','pdf.fonttype':42})
 fig,ax=plt.subplots(figsize=(12,11));ax.imshow(Image.open(OUT/'satellite.png'))
 for key,(a,b) in roads.items():ax.plot([a[0],b[0]],[a[1],b[1]],color='#00e5ff',lw=1.4,alpha=.8)
 # Draw the digitized bay rectangles at their local configured headings.
 m_per_px=math.dist(local((500,500)),local((501,500)))
 for s in slots:
  x,y=s['source_pixel'];angle=math.radians(s['heading_deg']);u=(math.sin(angle),-math.cos(angle));v=(math.cos(angle),math.sin(angle));l=s['length_m']/m_per_px/2;w=s['width_m']/m_per_px/2
  poly=[(x+su*l*u[0]+sv*w*v[0],y+su*l*u[1]+sv*w*v[1]) for su,sv in [(-1,-1),(-1,1),(1,1),(1,-1)]]
  ax.add_patch(Polygon(poly,fill=False,edgecolor='#ffad33' if s['parking_kind']=='on_street' else '#5aff78',linewidth=.9))
 for i,d in enumerate(dests,1):
  x,y=[p for name,p in [('Coal Creek Coffee',(425,694)),('Dukes',(579,778)),('Bent',(572,836)),('Green',(564,899)),('Altitude',(759,1015)),('Born',(420,217)),('Crowbar',(796,315)),('Sweet',(380,365))]][i-1];ax.text(x,y,str(i),ha='center',va='center',color='black',fontsize=12,bbox=dict(boxstyle='circle',facecolor='white',edgecolor='black',pad=.25))
 for key in ('g00','g01','g02','g20','g21','g22'):
  p=verts[key];ax.scatter(*p,marker='D',s=55,color='#ff66dd',edgecolor='black',zorder=5)
 for label,x,y in [('E Ivinson Avenue',1100,145),('Grand Avenue',1100,647),('E Garfield Street',1090,1125),('S 1st Street',370,450),('S 2nd Street',846,450),('S 3rd Street',1330,450)]:
  ax.text(x,y,label,fontsize=10,color='white',ha='center',rotation=90 if 'Street' in label and not label.startswith('E ') else 0,bbox=dict(facecolor='black',alpha=.65,edgecolor='none',pad=2))
 ax.set_xlim(285,1390);ax.set_ylim(1190,50);ax.axis('off')
 fig.text(.10,.045,'Orange: provisional 2-hour street bays   Green: off-street bays\nCyan: draft vehicle network   White numbers: destinations   Magenta: boundary access',fontsize=12)
 fig.text(.1,.012,'REVIEW DRAFT — space counts, restrictions, entrances and street directions require confirmation.\nImagery: Esri and imagery providers.',fontsize=10)
 fig.savefig(OUT/'downtown_layout_review.png',dpi=180,bbox_inches='tight');fig.savefig(OUT/'downtown_layout_review.pdf',bbox_inches='tight');plt.close(fig)
 summary=dict(spaces=len(slots),on_street=sum(s['parking_kind']=='on_street' for s in slots),off_street=sum(s['parking_kind']=='off_street' for s in slots),destinations=len(dests),paired_access_points=len(entries),simulation_executed=False)
 # Local interactive review: no browser APIs or simulation execution required.
 import html
 svg=[]
 for key,(a,b) in roads.items():svg.append(f'<path class="road" d="M {a[0]} {a[1]} L {b[0]} {b[1]}"/>')
 for slot in slots:
  x,y=slot['source_pixel'];kind=slot['parking_kind'];tip=html.escape(f"{slot['id']} | {slot['module']} | {slot['time_limit_minutes'] or 'No configured'} min | estimated centre; restrictions require review")
  svg.append(f'<circle class="{kind}" cx="{x}" cy="{y}" r="5"><title>{tip}</title></circle>')
 for d in dests:
  # invert the same geographic transform via nearest stored destination pixel
  idx=int(d['id'][-2:])-1
  x,y=[(425,694),(579,778),(572,836),(564,899),(759,1015),(420,217),(796,315),(380,365)][idx]
  svg.append(f'<g class="destination"><circle cx="{x}" cy="{y}" r="14"/><text x="{x}" y="{y+5}">{idx+1}</text><title>{html.escape(d["name"])}</title></g>')
 names=''.join(f'<li>{html.escape(d["name"])} — assumed entrance</li>' for d in dests)
 doc='<!doctype html><meta charset="utf-8"><title>Downtown layout review</title><style>body{font:16px system-ui;margin:20px;background:#f4f6f6}main{display:grid;grid-template-columns:minmax(600px,1fr) 320px;gap:20px}svg{width:100%;background:white}.road{stroke:#00e5ff;stroke-width:3;fill:none}.on_street{fill:#ffad33;stroke:black}.off_street{fill:#5aff78;stroke:black}.destination circle{fill:white;stroke:black;stroke-width:2}.destination text{text-anchor:middle;font-weight:bold}label{display:block;margin:12px 0}</style><h1>Downtown Laramie — review draft</h1><p>No simulations have been executed. Hover over spaces for IDs and provisional restrictions.</p><main><svg viewBox="280 40 1120 1160"><image href="satellite.png" width="1536" height="1280"/>'+''.join(svg)+'</svg><aside><b>Layers</b>'+''.join(f'<label><input type="checkbox" checked data-layer="{c}">{t}</label>' for c,t in [('on_street','Orange: provisional two-hour street spaces'),('off_street','Green: off-street spaces'),('road','Cyan: draft vehicle network'),('destination','Fixed destinations')])+'<ol>'+names+'</ol><p>Check counts, angles, entrances, curb cuts, parking signs and street directions. Accessible and loading designations remain unverified. Walking currently uses straight-line distances.</p><a href="environment.review.json" download>Download environment JSON</a><p>Imagery: Esri and imagery providers.</p></aside></main>'
 doc += "<script>document.querySelectorAll('input[data-layer]').forEach(i=>i.onchange=()=>document.querySelectorAll('.'+i.dataset.layer).forEach(e=>e.style.display=i.checked?'':'none'));</script>"
 (OUT/'layout_review.html').write_text(doc,encoding='utf8')
 (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':main()
