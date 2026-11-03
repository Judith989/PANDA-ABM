"""Plot configured landmarks on the satellite screenshot used in site review.

Geographic anchors belong to this exact screenshot. This is a cartographic
research figure, not a surveyed georeference or regenerated aerial photograph.
"""
from pathlib import Path
import hashlib
import json
import math
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'research/site_assets'
OUTPUT=ROOT/'paper/results_section/figures'
OUTPUT.mkdir(parents=True,exist_ok=True)
SOURCE=ASSETS/'walmart_satellite_source.jpg'
ANCHOR_A=(-105.541668,41.303614)
ANCHOR_B=(-105.537377,41.301196)


def pixel(lon,lat):
    def mercator(value):return math.log(math.tan(math.pi/4+math.radians(value)/2))
    return (550+(lon-ANCHOR_A[0])*400/(ANCHOR_B[0]-ANCHOR_A[0]),
            250+(mercator(lat)-mercator(ANCHOR_A[1]))*300/(mercator(ANCHOR_B[1])-mercator(ANCHOR_A[1])))


def main(*, layout=False):
    config=json.loads((ROOT/'data/lot_config.json').read_text())
    photo=np.asarray(Image.open(SOURCE).convert('RGB'))
    assert photo.shape[:2]==(720,1280),'Geographic anchors require the original screenshot'
    fig=plt.figure(figsize=(7.2,7.5) if layout else (7.2,7.0),facecolor='white')
    ax=fig.add_axes([.025,.20,.95,.79] if layout else [.025,.13,.95,.86])
    ax.imshow(photo)
    ax.set_xlim(520,950);ax.set_ylim(590,200);ax.set_aspect('equal');ax.set_axis_off()
    layout_records = {}
    if layout:
        from panda_abm.environment.facility import load_facility_from_lot_config
        from panda_abm.environment.navigation import AisleNetwork
        from matplotlib.lines import Line2D
        facility = load_facility_from_lot_config(ROOT/'data/lot_config.json')
        navigation = AisleNetwork(facility)
        meta = config['meta']
        def local_pixel(point):
            x,y=point
            return pixel(meta['ref_lon']+x/(111000*math.cos(math.radians(meta['ref_lat']))), meta['ref_lat']+y/111000)
        stalls=set(navigation.space_nodes.values())
        for a,b in navigation.graph.edges():
            points=np.array([local_pixel(navigation.positions[n]) for n in (a,b)])
            spur=a in stalls or b in stalls
            line,=ax.plot(points[:,0],points[:,1],color='#ff6b00',lw=.3 if spur else 1.45,alpha=.3 if spur else .95,zorder=2)
            if not spur:line.set_path_effects([pe.Stroke(linewidth=2.7,foreground='white'),pe.Normal()])
        categories=[('usable',lambda s:not s['is_unavailable'] and not s['is_accessible'],'#00d9ff','o',4),('accessible',lambda s:not s['is_unavailable'] and s['is_accessible'],'#9dff60','s',12),('unavailable',lambda s:s['is_unavailable'],'#ff79d1','x',7)]
        counts={}
        for name,predicate,color,marker,size in categories:
            selected=[s for s in config['slots'] if predicate(s)]
            points=np.array([pixel(s['lon'],s['lat']) for s in selected])
            counts[name]=len(selected)
            ax.scatter(points[:,0],points[:,1],s=size,c=color,marker=marker,linewidths=.45,zorder=3)
        legend=[Line2D([],[],color='#00d9ff',marker='o',ls='',markersize=4,label=f"Other usable ({counts['usable']:,})"),Line2D([],[],color='#9dff60',marker='s',ls='',markersize=5,label=f"Accessible ({counts['accessible']:,})"),Line2D([],[],color='#ff79d1',marker='x',ls='',markersize=5,label=f"Unavailable ({counts['unavailable']:,})"),Line2D([],[],color='#ff6b00',lw=2,label='Simulated aisle network')]
        fig.legend(handles=legend,loc='lower center',bbox_to_anchor=(.5,.095),ncol=2,fontsize=9,frameon=False,columnspacing=1.3,handletextpad=.5,prop={'weight':'bold','size':9})
        layout_records=dict(slot_count=len(config['slots']),category_counts=counts,aisle_count=len(navigation.aisle_nodes),graph_nodes=len(navigation.positions),graph_edges=navigation.graph.number_of_edges(),network_source='panda_abm.environment.navigation.AisleNetwork; runtime topology, including approach spurs',navigation_sha256=hashlib.sha256((ROOT/'panda_abm/environment/navigation.py').read_bytes()).hexdigest())
        assert sum(counts.values())==len(config['slots'])==len(facility.spaces)
        print(layout_records)
    positions={'door_1':(565,477),'door_2':(747,492),'exit_a':(625,214),'exit_b':(929,377)}
    if layout:positions.update(door_1=(620,480),door_2=(710,520))
    records=[]
    for group,color in (('walmart_doors','#087eab'),('parking_lot_exits','#edb925')):
        for point in config[group]:
            x,y=pixel(point['lon'],point['lat']);key=point['id'];door=key.startswith('door')
            short=('D'+key[-1]) if door else key[-1].upper()
            label={'door_1':'Door 1 (west)','door_2':'Door 2 (east)','exit_a':'Entry/Exit A (north)','exit_b':'Entry/Exit B (east)'}[key]
            ax.scatter(x,y,s=350,c=color,edgecolors='white',linewidths=2,zorder=5)
            ax.text(x,y,short,ha='center',va='center',color='white' if door else '#14212b',weight='bold',fontsize=11,zorder=6)
            annotation=ax.annotate(label,xy=(x,y),xytext=positions[key],ha='right' if key=='exit_b' else 'center',
                va='center',fontsize=11,weight='bold',color='#14212b',zorder=7,
                bbox=dict(boxstyle='round,pad=.4',fc='white',ec=color,lw=1.6),
                arrowprops=dict(arrowstyle='-',color=color,lw=2,shrinkB=13))
            annotation.arrow_patch.set_path_effects([pe.Stroke(linewidth=4,foreground='white'),pe.Normal()])
            records.append(dict(id=key,label=label,lat=point['lat'],lon=point['lon'],image_x=x,image_y=y))
    ax.annotate('N',xy=(928,214),xytext=(928,244),ha='center',va='center',fontsize=12,weight='bold',color='white',arrowprops=dict(arrowstyle='-|>',color='white',lw=2),path_effects=[pe.withStroke(linewidth=3,foreground='#14212b')])
    if not layout:fig.text(.5,.108,'D1 / D2: Walmart doors     A / B: vehicle entry and exit',ha='center',fontsize=11)
    # Preserve the original map branding and attribution pixels beneath the
    # cropped study view; retain the full unchanged source alongside the figure.
    logo=fig.add_axes([.42,.06,.16,.035]);logo.imshow(photo[679:700,600:760]);logo.set_axis_off()
    credit=fig.add_axes([.01,.025,.98,.025]);credit.imshow(photo[705:720,460:1280]);credit.set_axis_off()
    stem='walmart_simulated_layout' if layout else 'walmart_site_annotated'
    fig.savefig(OUTPUT/(stem+'.png'),dpi=350)
    fig.savefig(OUTPUT/(stem+'.pdf'))
    plt.close(fig)
    provenance=dict(source='Google Maps screenshot used in the earlier site review',
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        config_sha256=hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest(),
        image_size=[1280,720],projection='Mercator interpolation from two manually read screenshot anchors',
        anchors=[dict(lon=ANCHOR_A[0],lat=ANCHOR_A[1],pixel=[550,250]),dict(lon=ANCHOR_B[0],lat=ANCHOR_B[1],pixel=[950,550])],
        landmarks=records,simulated_layout=layout_records,note='Estimated alignment, not a survey. Source pixels are plotted with scientific annotations; no aerial content is generated.')
    (OUTPUT/(stem+'_provenance.json')).write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(OUTPUT/(stem+'.png'))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--layout',action='store_true',help='Overlay configured space centres and the actual simulation aisle graph')
    main(layout=parser.parse_args().layout)
