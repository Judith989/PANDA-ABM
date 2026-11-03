"""Native diagrams.net reconstruction; every diagram object remains editable."""
from pathlib import Path
import xml.etree.ElementTree as ET
import html
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'paper/figures/framework_physical_virtual_editable.drawio'
mx=ET.Element('mxfile',host='app.diagrams.net',version='26.0.0')
diagram=ET.SubElement(mx,'diagram',id='panda-framework',name='Parking digital-twin framework')
model=ET.SubElement(diagram,'mxGraphModel',dx='1800',dy='1250',grid='1',gridSize='10',guides='1',tooltips='1',connect='1',arrows='1',fold='1',page='1',pageScale='1',pageWidth='1800',pageHeight='1250',math='1',shadow='0')
root=ET.SubElement(model,'root');ET.SubElement(root,'mxCell',id='0');ET.SubElement(root,'mxCell',id='1',parent='0')
counter=0
def box(text,x,y,w,h,fill='#ffffff',stroke='#36566c',size=16,bold=False,parent='1',style=''):
 global counter
 counter+=1;i=f'n{counter}'
 s=f'rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontColor=#173449;fontFamily=Arial;fontSize={size};fontStyle={1 if bold else 0};arcSize=7;spacing=6;'+style
 c=ET.SubElement(root,'mxCell',id=i,value=text,style=s,vertex='1',parent=parent)
 ET.SubElement(c,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),attrib={'as':'geometry'})
 return i
def text(t,x,y,w,h=26,size=15,bold=False,parent='1',align='left'):
 return box(t,x,y,w,h,'none','none',size,bold,parent,f'rounded=0;align={align};verticalAlign=middle;')
def edge(a,b,label='',dashed=False,color='#1767ab',points=None,extra=''):
 global counter
 counter+=1
 s=f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeWidth=2;strokeColor={color};fontColor={color};fontFamily=Arial;fontSize=13;labelBackgroundColor=#ffffff;'+('dashed=1;dashPattern=6 4;' if dashed else '')+extra
 c=ET.SubElement(root,'mxCell',id=f'e{counter}',value=label,style=s,edge='1',parent='1',source=a,target=b)
 g=ET.SubElement(c,'mxGeometry',relative='1',attrib={'as':'geometry'})
 if points:
  arr=ET.SubElement(g,'Array',attrib={'as':'points'})
  for x,y in points:ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
 return c
def panel(title,x,y,w,h,fill):
 p=box('',x,y,w,h,fill,size=18)
 text(title,10,5,w-20,34,19,True,p)
 return p
def car(x,y,parent,color='#3477ae',scale=1):
 c=box('',x,y,13*scale,25*scale,color,'#173449',parent=parent,style='arcSize=30;')
 box('',2*scale,4*scale,9*scale,5*scale,'#d9edf6','none',parent=c)
 return c
def person(x,y,parent,color='#5689aa'):
 box('',x+6,y,15,15,'#f2c69d','#36566c',parent=parent,style='shape=ellipse;')
 box('',x,y+17,28,22,color,'#36566c',parent=parent)
def parking(parent,x,y,w=230,h=145):
 building=box('Store',x,y+h-27,w,27,'#e9e5dd',size=13,parent=parent)
 for label,xx in [('D1',x+35),('D2',x+w-60)]:text(label,xx,y+h-24,30,20,11,True,parent)
 for row in range(3):
  for col in range(9):
   xx=x+8+col*(w-16)/9;yy=y+8+row*34
   bay=box('',xx,yy,(w-26)/9,26,'#e0f1ef','#85aaa8',parent=parent,style='rounded=0;strokeWidth=.7;')
   if (row+col)%3==0:car(xx+4,yy+1,parent,scale=.8)
 text('A',x+2,y-16,25,20,12,True,parent);text('B',x+w-20,y+65,25,20,12,True,parent)
 # Road centreline: editable native connector without arrowhead.
 edge(building,building,'',color='#b3c1c8',points=None,extra='endArrow=none;strokeWidth=0;opacity=0;')
 return building

# Physical and virtual boundaries.
physical=panel('Physical parking facility',20,20,285,1070,'#edf6fc')
text('Physical counterpart (schematic)',12,46,260,35,15,True,physical)
parking(physical,22,110,240,200)
for yy,title,detail in [(360,'Spaces and aisles','Painted bays · doors · access points'),(505,'Drivers and vehicles','Arrivals · search · parking · departure'),(650,'Facility configuration','Estimated geometry and configured state')]:
 box(title,15,yy,255,43,'#ffffff',size=16,bold=True,parent=physical)
 text(detail,25,yy+48,235,55,14,parent=physical)
for j in range(4):car(35+j*53,850,physical,scale=1.7)
text('Illustrations describe the represented<br>facility; they are not measured data.',20,945,245,60,13,parent=physical)
virtual=panel('Virtual representation and behavioral simulation',390,20,1070,1070,'#f7fbfe')
env=panel('(i) Geospatial parking environment',410,75,335,290,'#e6f1fb')
parking(env,15,60,220,145)
text('Geometry · restrictions<br>Occupancy · aisle graph',15,220,305,50,14,parent=env)
pop=panel('(ii) Driver population generator',765,75,335,290,'#e7f6ef')
for yy,title,detail in [(60,'Trips and constraints','Arrival, destination, vehicle, eligibility'),(130,'Continuous preferences','Utility weights, temperature, CPT'),(200,'Reference expectations','Walking, exit distance, search time')]:
 person(15,yy,pop);text(title,55,yy,265,25,14,True,pop);text(detail,55,yy+25,265,36,12,parent=pop)
info=panel('(iv) Information service',1120,75,320,290,'#fff2df')
for j,label in enumerate(['Local','Aisle','Space']):
 sub=box(label,12+j*101,63,94,50,'#ffffff',size=15,bold=True,parent=info)
 for k in range(3):box('',17+j*101+k*25,125,19,44,'#45aaa5' if (j==1 or k==j) else '#e8eef2','#76909d',parent=info)
text('Reported opportunities<br>Counts or individual spaces<br>Observation timestamps',18,192,286,73,14,parent=info)
beh=panel('(iii) Behavioral decision layer',410,425,1030,335,'#f0eafd')
text('Shared candidate utility',265,47,480,26,17,True,beh,'center')
formula=box('U<sub>is</sub>(t) = ∑<sub>k=1</sub><sup>K</sup> β<sub>ik</sub> φ<sub>k</sub>(f<sub>isk</sub>(t))',240,78,540,50,'#ffffff','#ad92ca',21,parent=beh)
filter_=box('Feasibility<br><br>Vehicle · permit<br>Eligibility<br>Walking limit<br>Remaining time',15,145,160,157,'#ffffff','#ad92ca',14,parent=beh)
m0=box('<b>M0: deterministic utility</b><br><br>s* = arg max<sub>s ∈ ℱᵢ(t)</sub> U<sub>is</sub>(t)<br><br>Accept if U<sub>is*</sub>(t) ≥ θ<sub>i</sub>',195,150,258,125,'#e6f3fc','#69a9db',16,parent=beh)
m1=box('<b>M1: stochastic utility</b><br><br>P<sub>i</sub>(s) = exp(U<sub>is</sub>/τ<sub>i</sub>) /<br>∑<sub>j ∈ ℱᵢ(t)</sub> exp(U<sub>ij</sub>/τ<sub>i</sub>)<br><br>Sample; then apply threshold',468,150,258,125,'#fff2db','#dfba74',15,parent=beh)
cpt=box('<b>CPT: reference-dependent prospects</b><br><br>Δ<sub>is</sub><sup>o</sup> = U<sub>i</sub>(f<sub>is</sub><sup>o</sup>) − U<sub>i</sub>(f<sub>i</sub><sup>ref</sup>)<br><br>Aspiration and continuation',741,150,272,125,'#fceaf1','#d99cb5',15,parent=beh)
decision=box('Target or continue',390,291,260,32,'#ffffff','#ad92ca',16,True,beh)
for node in (m0,m1,cpt):edge(filter_,node,extra='exitX=1;exitY=.5;entryX=0;entryY=.5;');edge(node,decision,extra='exitX=.5;exitY=1;entryX=.5;entryY=0;')
engine=panel('(v) Simulation engine',410,815,1030,255,'#e5f3fc')
labels=['Enter','Search aisles','Evaluate','Accept?','Approach','Claim','Available?','Park','Walk / activity / return','Depart']
nodes=[]
for j,label in enumerate(labels):
 n=box(label,14+j*100,64,92,61,'#ffffff' if '?' not in label else '#fff1d7',size=13,bold=True,parent=engine,style='shape=rhombus;' if '?' in label else '')
 nodes.append(n)
 if j:edge(nodes[j-1],n,'Yes' if j in (4,7) else '',extra='exitX=1;exitY=.5;entryX=0;entryY=.5;')
edge(nodes[3],nodes[1],'No: continue search',color='#c64045',points=[(770,985),(570,985)],extra='exitX=.5;exitY=1;entryX=.5;entryY=1;')
edge(nodes[6],nodes[1],'No: failed claim',color='#c64045',points=[(1070,1015),(570,1015)],extra='exitX=.5;exitY=1;entryX=.5;entryY=1;')
abandon=box('Abandon',865,205,145,34,'#ffffff','#c69744',14,True,engine)
edge(nodes[1],abandon,'Search deadline',color='#c69744',points=[(570,1040),(1300,1040)],extra='dashed=1;dashPattern=1 3;exitX=.5;exitY=1;entryX=0;entryY=.5;')
text('Elapsed search includes movement, approaches and failed attempts.',18,177,780,27,13,parent=engine)

support=panel('Decision support',1545,20,235,1070,'#eaf8f5')
text('Cesium interface',12,50,210,35,18,True,support,'center');parking(support,12,110,210,150)
text('Georeferenced scene<br>States and trajectories',15,285,205,55,14,parent=support)
controls=box('<b>Scenario controls</b><br><br>Arrival interval<br>Initial occupancy<br>Information mode<br>Decision model',12,375,210,200,'#ffffff','#5da8a5',15,parent=support)
outputs=box('<b>Illustrative outcomes</b><br><br>Search time<br>Walking distance<br>Parking success<br>Competition',12,690,210,200,'#ffffff','#5da8a5',15,parent=support)
for j,hh in enumerate([40,65,25,50]):box('',25+j*40,975-hh,22,hh,'#3983bd','none',parent=support)
text('Illustrative only',15,995,200,30,12,parent=support,align='center')
# Cross-component relationships use explicit ports and open corridors.
edge(physical,env,'Estimated geometry;<br>configured initial state',extra='exitX=1;exitY=.12;entryX=0;entryY=.25;')
edge(physical,env,'Observed-state updates<br>(proposed)',True,'#808080',extra='exitX=1;exitY=.25;entryX=0;entryY=.7;')
edge(env,info,'Parking state',points=[(680,55),(1280,55)],extra='exitX=.8;exitY=0;entryX=.5;entryY=0;')
edge(pop,beh,'Driver context',extra='exitX=.5;exitY=1;entryX=.5;entryY=0;')
edge(info,beh,'Observations',extra='exitX=.5;exitY=1;entryX=.87;entryY=0;')
edge(beh,engine,'Decisions',extra='exitX=.5;exitY=1;entryX=.5;entryY=0;')
edge(engine,env,'Occupancy update',points=[(400,790),(400,385)],extra='exitX=0;exitY=.15;entryX=0;entryY=1;')
edge(engine,support,'Simulated states<br>and outcomes',points=[(1495,900),(1495,300)],extra='exitX=1;exitY=.5;entryX=0;entryY=.3;')
edge(controls,virtual,'Scenario settings',extra='exitX=0;exitY=.5;entryX=1;entryY=.5;')
edge(support,physical,'Proposed management interventions',True,'#808080',points=[(1660,1140),(165,1140)],extra='exitX=.5;exitY=1;entryX=.5;entryY=1;')
text('Solid: implemented connections     Dashed grey: proposed extensions     Dotted amber: search-deadline transition',320,1180,1250,40,15,align='center')
ET.indent(mx,space='  ');ET.ElementTree(mx).write(out,encoding='utf-8',xml_declaration=True)
cells=root.findall('mxCell');ids=[c.get('id') for c in cells];assert len(ids)==len(set(ids))
for c in cells:
 if c.get('edge')=='1':assert c.get('source') in ids and c.get('target') in ids
print(f'Wrote {out}; {len(cells)} native editable objects; valid XML and edge endpoints.')
