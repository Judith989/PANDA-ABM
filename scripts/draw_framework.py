"""Publication architecture diagram: editable SVG, vector PDF and 400-dpi PNG."""
from pathlib import Path
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'paper/figures';OUT.mkdir(parents=True,exist_ok=True)
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'font.weight':'bold','pdf.fonttype':42,'svg.fonttype':'none'})
fig,ax=plt.subplots(figsize=(12.5,10));ax.set_xlim(0,12.5);ax.set_ylim(0,10);ax.axis('off')
ink='#193347';blue='#dcecf5';green='#e3f0e9';orange='#fbecd9';purple='#eee7f4'
def card(x,y,w,h,title,items,color):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.025,rounding_size=.10',facecolor='white',edgecolor=ink,lw=1.4,zorder=2))
    ax.add_patch(FancyBboxPatch((x+.04,y+h-.47),w-.08,.43,boxstyle='round,pad=0.015,rounding_size=.06',facecolor=color,edgecolor='none',zorder=3))
    ax.text(x+.15,y+h-.25,title,fontsize=11.0,color=ink,va='center',zorder=4)
    step=(h-.65)/len(items)
    for j,(label,detail) in enumerate(items):
        yy=y+h-.67-j*step
        ax.text(x+.14,yy,label,fontsize=10.8,color=ink,va='top',zorder=4)
        if detail:ax.text(x+.14,yy-.21,'\n'.join(textwrap.fill(part,width=int(w*10.8)) for part in detail.split('\n')),fontsize=9.5,fontweight='normal',color='#253d4d',va='top',linespacing=1.2,zorder=4)
def arrow(points,label=None,labelpos=None,dashed=False,color=ink):
    for a,b in zip(points[:-2],points[1:-1]):ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=1.5,ls='--' if dashed else '-',zorder=1)
    ax.add_patch(FancyArrowPatch(points[-2],points[-1],arrowstyle='-|>',mutation_scale=14,lw=1.5,color=color,linestyle='--' if dashed else '-',zorder=1))
    if label:ax.text(*labelpos,label,fontsize=10.4,color=color,ha='center',va='center',bbox=dict(facecolor='white',edgecolor='none',pad=1),zorder=5)
card(.25,7.15,5.65,2.45,'(i) Geospatial parking environment',[
 ('Static facility','Spaces, restrictions, doors, Entry/Exit A and B'),
 ('Spatial representation','Local metric coordinates and connected aisle graph'),
 ('Shared dynamic state','Occupied / free spaces and driver activity')],blue)
card(6.6,7.15,5.65,2.45,'(ii) Driver population generator',[
 ('Trip attributes and constraints','Arrival, destination, vehicle, eligibility, walking limit'),
 ('Continuous preferences','Utility weights, choice temperature, CPT parameters'),
 ('Reference expectations','Search expectation; compatible-inventory distances')],green)
card(.25,3.45,3.65,2.9,'(iv) Information service',[
 ('Unaided search','Local space observations'),
 ('Aisle-level information','Compatible free counts; aisle routing'),
 ('Space-level information','Reported spaces and remote targets'),
 ('Observation metadata','Report time and believed availability')],blue)
card(4.45,3.45,3.65,2.9,'(iii) Behavioral decision layer',[
 ('Candidate feasibility','Vehicle, permit, access, walk, time'),
 ('Utility mechanisms','M0 (maximum); M1 (stochastic)'),
 ('CPT mechanism','Reference-dependent prospects'),
 ('Decision','Accept target or continue search')],purple)
card(8.65,3.45,3.6,2.9,'(v) Simulation engine',[
 ('Movement and time','Aisle routing and elapsed search'),
 ('Competition','Exclusive claims and failed attempts'),
 ('Driver lifecycle','Park, walk, activity, return, exit'),
 ('State transitions','Occupancy, events and abandonment')],orange)
arrow([(2.05,7.15),(2.05,6.35)],'Occupancy and geometry',(2.05,6.78))
arrow([(9.35,7.15),(9.35,6.8),(6.27,6.8),(6.27,6.35)],'Driver-specific context',(6.9,7.0))
arrow([(3.9,4.93),(4.45,4.93)])
arrow([(8.1,4.93),(8.65,4.93)])
ax.text(4.17,5.45,'Observe',rotation=90,fontsize=10.5,color=ink,ha='center')
ax.text(8.37,5.45,'Act',rotation=90,fontsize=10.5,color=ink,ha='center')
# Physical state feedback is routed in the open band above the five components.
arrow([(10.6,6.35),(10.6,6.58),(4.9,6.58),(4.9,7.15)],'Movement and claims update shared state',(7.4,6.58))
card(.25,.4,5.65,2.25,'Recorded outputs',[
 ('Event and trajectory records','Observations, decisions, targets, claims, occupancy'),
 ('Individual and collective measures','Search time, success, walking, exit proximity,\ncompetition and spatial parking patterns')],green)
card(6.6,.4,5.65,2.25,'Digital-twin interface: Cesium',[
 ('Georeferenced 3D scene','Vehicle trajectories and parking-space states'),
 ('Interactive scenario exploration','Decision rule, information, occupancy, population,\narrival interval and seed; replay and live stepping')],blue)
arrow([(10.65,3.55),(10.65,3.12),(3.05,3.12),(3.05,2.65)],'Timestamped simulation states and events',(6.2,3.12))
arrow([(10.65,3.12),(10.65,2.65)])
# A separate future extension, not part of the five implemented components.
ax.text(6.25,.07,'Solid arrows: implemented interactions     |     Dashed arrow: future observation assimilation',ha='center',fontsize=10,color=ink)
arrow([(.25,8.38),(.07,8.38),(.07,9.88),(4.4,9.88),(4.4,9.6)],'External observations (future)',(2.3,9.88),dashed=True,color='#737373')
for ext in ('svg','pdf','png'):fig.savefig(OUT/f'framework_architecture.{ext}',dpi=400,bbox_inches='tight',pad_inches=.12)
plt.close(fig)
print(OUT/'framework_architecture.pdf')
