"""Embed generated transparent illustrations into a native editable draw.io file.

The PNGs are embedded unchanged; labels, equations, shapes and edges stay native.
"""
from pathlib import Path
import base64,json,hashlib,xml.etree.ElementTree as ET
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];F=ROOT/'paper/figures';A=F/'framework_assets'
source=F/'framework_physical_virtual_editable.drawio'
dest=F/'framework_with_transparent_images.drawio'
tree=ET.parse(source);root=tree.getroot().find('./diagram/mxGraphModel/root')
counter=2000
def node(label):
 heading=next(c for c in root.findall('mxCell') if c.get('vertex')=='1' and c.get('value')==label)
 parent=heading.get('parent')
 return next(c for c in root if c.get('id')==parent) if parent!='1' else heading
def geom(c):return c.find('mxGeometry')
def all_desc(parent):
 ids={parent};changed=True
 while changed:
  before=len(ids);ids|={c.get('id') for c in root if c.get('parent') in ids};changed=len(ids)>before
 return ids-{parent}
def clear_panel(panel):
 ids=all_desc(panel.get('id'))
 # Retain first heading cell; remove old native thumbnail primitives and edges.
 heading=next(c for c in root if c.get('parent')==panel.get('id') and c.get('value'))
 ids.discard(heading.get('id'))
 for c in list(root):
  if c.get('id') in ids or c.get('source') in ids or c.get('target') in ids:root.remove(c)
 return panel.get('id')
def shape(value,x,y,w,h,parent,style):
 global counter
 counter+=1;c=ET.SubElement(root,'mxCell',id=f'art{counter}',value=value,style=style,vertex='1',parent=parent)
 ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
 return c
def text(value,x,y,w,h,parent,size=15,bold=False):
 return shape(value,x,y,w,h,parent,f'text;html=1;whiteSpace=wrap;overflow=hidden;align=left;verticalAlign=middle;fontFamily=Arial;fontSize={size};fontColor=#173449;fontStyle={1 if bold else 0};strokeColor=none;fillColor=none;')
def image(name,x,y,w,h,parent):
 path=A/f'{name}.png';data=path.read_bytes();encoded=base64.b64encode(data).decode()
 # Fit visible alpha bounds without trimming, resampling or changing PNG bytes.
 im=Image.open(path);assert im.mode=='RGBA' and im.getchannel('A').getextrema()==(0,255),name
 # Ignore near-transparent fringe noise when measuring visible content only.
 left,top,right,bottom=im.getchannel('A').point(lambda v:255 if v>32 else 0).getbbox()
 scale=min(w/(right-left),h/(bottom-top))
 x=x+(w-(right-left)*scale)/2-left*scale
 y=y+(h-(bottom-top)*scale)/2-top*scale
 w,h=im.width*scale,im.height*scale
 # mxGraph's image data URI syntax omits ';base64' to preserve style delimiters.
 return shape('',x,y,w,h,parent,'shape=image;verticalLabelPosition=bottom;verticalAlign=top;imageAspect=1;aspect=fixed;image=data:image/png,'+encoded+';')

physical=node('Physical parking facility');pid=clear_panel(physical)
text('Physical counterpart (schematic)',14,43,255,35,pid,14,True)
image('physical_facility',12,88,260,490,pid)
image('physical_context_details',12,600,260,95,pid)
for yy,label,detail in [(725,'Spaces and aisles','Marked bays, doors and vehicle accesses'),(815,'Drivers and vehicles','Entering, searching, parking and leaving'),(905,'Facility representation','Estimated geometry; configured initial state')]:
 text(label,15,yy,255,28,pid,16,True);text(detail,15,yy+30,255,45,pid,14)
text('Illustrative facility, not a surveyed image.',15,1010,255,35,pid,12)

env=node('(i) Geospatial parking environment');eid=clear_panel(env)
image('virtual_lot_topdown',10,52,205,200,eid)
text('Geometry<br><br>Restrictions<br><br>Occupancy',222,64,102,150,eid,13,True)
text('Door 1 / Door 2 · Access A / B<br>Connected aisle graph',14,252,305,32,eid,12)
pop=node('(ii) Driver population generator');popid=clear_panel(pop)
image('driver_population',10,48,78,225,popid)
for yy,label,detail in [(53,'Trips and constraints','Arrival, destination, vehicle,<br>eligibility and walking limit'),(132,'Continuous preferences','Utility weights, temperature<br>and CPT parameters'),(211,'Reference expectations','Walking, exit distance<br>and search duration')]:
 text(label,100,yy,223,23,popid,14,True);text(detail,100,yy+24,223,44,popid,12)
info=node('(iv) Information service');iid=clear_panel(info)
for j,label in enumerate(['Local','Aisle','Space']):text(label,13+j*102,57,96,30,iid,15,True)
image('information_views',12,92,296,110,iid)
text('Reported opportunities<br>Local vision; aisle counts; space identities<br>Observation timestamps',15,212,290,65,iid,13)

support=node('Decision support')
# Preserve the controls/output cards, remove the old miniature lot and its child bays.
sid=support.get('id')
for c in list(root):
 if c.get('parent')==sid:
  g=geom(c)
  if g is not None and 90<=float(g.get('y',0))<275:
   descendants=all_desc(c.get('id'))|{c.get('id')}
   for z in list(root):
    if z.get('id') in descendants or z.get('source') in descendants or z.get('target') in descendants:root.remove(z)
image('cesium_scene',10,88,215,190,sid)

beh=node('(iii) Behavioral decision layer');bid=beh.get('id')
filter_=next(c for c in root if c.get('parent')==bid and 'Feasibility' in c.get('value',''))
models=[next(c for c in root if c.get('parent')==bid and phrase in c.get('value','')) for phrase in ['M0: deterministic','M1: stochastic','CPT: reference']]
# Route feasibility/model connections above and below cards, not through formulas.
for c in root.findall('mxCell'):
 if c.get('source')==filter_.get('id') and c.get('target') in {m.get('id') for m in models}:
  m=next(z for z in models if z.get('id')==c.get('target'));x=float(geom(m).get('x'))+410+float(geom(m).get('width'))/2
  c.set('style',c.get('style')+'exitX=1;exitY=0;entryX=.5;entryY=0;')
  g=geom(c)
  for child in list(g):g.remove(child)
  arr=ET.SubElement(g,'Array',attrib={'as':'points'})
  for xx,yy in [(590,565),(x,565)]:ET.SubElement(arr,'mxPoint',x=str(xx),y=str(yy))
 if c.get('source') in {m.get('id') for m in models}:
  m=next(z for z in models if z.get('id')==c.get('source'));x=float(geom(m).get('x'))+410+float(geom(m).get('width'))/2
  g=geom(c)
  for child in list(g):g.remove(child)
  arr=ET.SubElement(g,'Array',attrib={'as':'points'})
  for xx,yy in [(x,707),(930,707)]:ET.SubElement(arr,'mxPoint',x=str(xx),y=str(yy))

engine=node('(v) Simulation engine');engineid=engine.get('id')
# Expand lower virtual region to fit illustration strip above editable flowchart.
geom(engine).set('height','340')
virtual=node('Virtual representation and behavioral simulation');geom(virtual).set('height','1160')
# Move original lifecycle boxes and its notes down; preserve all native edges.
children=[c for c in root if c.get('parent')==engineid]
for c in children:
 g=geom(c)
 if g is not None and float(g.get('y',0))>=40:g.set('y',str(float(g.get('y'))+78))
image('driver_lifecycle',14,42,1000,100,engineid)
# Shift manual lifecycle connector bends to follow the moved native shapes.
enginedesc=all_desc(engineid)
for c in root:
 if c.get('edge')=='1' and c.get('source') in enginedesc and c.get('target') in enginedesc:
  for p in c.findall('./mxGeometry/Array/mxPoint'):p.set('y',str(float(p.get('y'))+78))
# Move lower external feedback/legend below expanded panel.
for c in root:
 if c.get('vertex')=='1' and c.get('parent')=='1' and c.get('value','').startswith('Solid:'):
  geom(c).set('y','1270')
 if c.get('edge')=='1' and c.get('value')=='Proposed management interventions':
  for p in c.findall('./mxGeometry/Array/mxPoint'):p.set('y','1230')
graph=tree.getroot().find('./diagram/mxGraphModel');graph.set('pageHeight','1340')

# Avoid overflows in long model titles, and keep mathematical text intact.
for c in models:c.set('style',c.get('style')+'fontSize=14;spacing=8;')
for c in root:
 if c.get('vertex')=='1' and c.get('parent')==engineid and '?' not in c.get('value',''):
  if c.get('value') in ['Walk / activity / return']:c.set('value','Walk / activity / return')

# A second editable page exposes the same assets for copy/paste and reuse.
main_root=root
library=ET.SubElement(tree.getroot(),'diagram',id='transparent-assets',name='Transparent PNG asset library')
libgraph=ET.SubElement(library,'mxGraphModel',grid='1',gridSize='10',page='1',pageScale='1',pageWidth='1800',pageHeight='1450',math='1')
root=ET.SubElement(libgraph,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
text('Transparent illustration library — copy, resize or replace individual image objects',25,15,1700,45,'1',24,True)
for name,x,y,w,h in [
 ('physical_facility',25,110,280,560),
 ('virtual_lot_topdown',350,110,360,360),
 ('cesium_scene',760,110,360,360),
 ('driver_population',1210,110,170,510),
 ('information_views',350,570,700,230),
 ('physical_context_details',25,890,740,245),
 ('driver_lifecycle',25,1240,1700,175)]:
 text(name+'.png',x,y-35,max(w,300),30,'1',17,True)
 image(name,x,y,w,h,'1')
root=main_root

ET.indent(tree,space='  ');tree.write(dest,encoding='utf-8',xml_declaration=True)
ids={c.get('id') for c in root}
for c in root:
 if c.get('edge')=='1':assert c.get('source') in ids and c.get('target') in ids,(c.get('id'),c.get('source'),c.get('target'))
embedded=[c for c in root if 'image=data:image/png,' in c.get('style','')]
assert len(embedded)==7
for c in embedded:
 raw=c.get('style').split('image=data:image/png,')[1].split(';')[0]
 assert base64.b64decode(raw).startswith(b'\x89PNG\r\n\x1a\n')
manifest={'drawio':dest.name,'embedded_pngs':7,'pages':2,'external_image_dependencies':False,'editable':'Native labels, equations, panels, process nodes and connectors; embedded raster illustrations movable/resizable/replacable.',
 'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [dest,*sorted(A.glob('*.png'))]}}
(A/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
print(f'Created {dest}; all 7 PNGs embedded and connector endpoints verified.')
