"""Source-matched site maps, clearly distinguishing estimates and fictional geometry."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parent))
from planning_study_engine import facility_for

def maps(out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from panda_abm.environment.pedestrian_geometry import bay_polygon
    out=Path(out);(out/'figures').mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':14,'font.weight':'bold','axes.labelweight':'bold'})
    metadata=[]
    for name in ('walmart_original','walmart_satellite','downtown','synthetic'):
        f=facility_for(name);fig,ax=plt.subplots(figsize=(10,10))
        usable=[s for s in f.spaces if not s.unavailable]
        network=f.aisle_network or {};seen=set()
        stall_centres={(round(s.x_m,6),round(s.y_m,6)) for s in f.spaces}
        for a,b in network.get('edges',[]):
            p,q=network['nodes'][a],network['nodes'][b];key=tuple(sorted((a,b)))
            if key in seen or any(tuple(round(v,6) for v in point) in stall_centres for point in (p,q)):continue
            seen.add(key);ax.plot([p[0],q[0]],[p[1],q[1]],color='#777777',lw=.9,zorder=1)
        for poly in network.get('building_footprints_m',{}).values():
            ax.add_patch(Polygon(poly,facecolor='#e8e8e8',edgecolor='#777777',lw=.8,zorder=0))
        geometry=network.get('bay_geometry',{})
        for accessible,color,label in [(False,'#0072B2','Other usable spaces'),(True,'#D55E00','Accessible spaces')]:
            ss=[s for s in usable if bool(s.accessible)==accessible]
            ax.scatter([],[],s=35,c=color,marker='s',label=label)
            for s in ss:
                slot=dict(local_x_m=s.x_m,local_y_m=s.y_m,**geometry.get(s.space_id,{}))
                ax.add_patch(Polygon(bay_polygon(slot),facecolor=color,edgecolor='white',lw=.2,zorder=2))
        for i,(x,y) in enumerate(f.walmart_doors):ax.scatter(x,y,marker='s',c='black',s=50);ax.annotate(f'D{i+1}',(x,y),xytext=(5,6),textcoords='offset points',fontsize=12,fontweight='bold')
        for i,(x,y) in enumerate(f.exit_points):ax.scatter(x,y,marker='D',c='#8c4a20',s=40);ax.annotate(f'A{i+1}',(x,y),xytext=(5,-12),textcoords='offset points',fontsize=12,fontweight='bold')
        ax.set_aspect('equal');ax.set_xlabel('Local east (m)');ax.set_ylabel('Local north (m)');ax.legend(loc='upper left',bbox_to_anchor=(0,-.08),ncol=2);ax.grid(alpha=.15)
        fig.savefig(out/'figures'/f'map_{name}.pdf',bbox_inches='tight');fig.savefig(out/'figures'/f'map_{name}.png',dpi=180,bbox_inches='tight');plt.close(fig)
        connected=sum(any(__import__('math').isfinite(f.walking_network.distance(s.space_id,d)) for d in f.walmart_door_ids) for s in usable) if f.walking_network else len(usable)
        metadata.append(dict(environment=name,records=len(f.spaces),nominal_usable=len(usable),accessible=sum(s.accessible for s in usable),walking_connected_any_destination=connected,walking_measure='network' if f.walking_network else 'straight_line',geometry='fictional transfer' if name=='synthetic' else 'estimated, not surveyed',destination_labels={f'D{i+1}':sid for i,sid in enumerate(f.walmart_door_ids)},access_labels={f'A{i+1}':sid for i,sid in enumerate(f.exit_point_ids)}))
    (out/'site_inventory.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')

if __name__=='__main__':maps(sys.argv[1])
