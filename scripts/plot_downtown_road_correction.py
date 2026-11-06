"""Review the corrected routes against the archived georeferenced source image."""
from pathlib import Path
import json
import math
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    from PIL import Image
    from panda_abm.environment.pedestrian_geometry import bay_polygon
    raw=json.loads((ROOT/'data/lot_config.downtown_laramie.json').read_text())
    info=json.loads((ROOT/'research/downtown_review/20261105/imagery.json').read_text())
    def pixel(p):
        lat=raw['meta']['ref_lat']+p[1]/111000
        lon=raw['meta']['ref_lon']+p[0]/(111000*math.cos(math.radians(raw['meta']['ref_lat'])))
        n=2**info['zoom'];x=((lon+180)/360*n-info['tile_x0'])*256
        y=((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n-info['tile_y0'])*256
        return x,y
    plt.rcParams.update({'font.size':13,'font.weight':'bold','pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(12,12))
    ax.imshow(Image.open(ROOT/'research/downtown_review/20261105/satellite.png'))
    for slot in raw['slots']:
        ax.add_patch(Polygon([pixel(p) for p in bay_polygon(slot)],facecolor='none',edgecolor='#ffbd42',linewidth=.6))
    net=raw['aisle_network'];seen=set()
    stalls={(round(s['local_x_m'],7),round(s['local_y_m'],7)) for s in raw['slots']}
    for a,b in net['edges']:
        key=tuple(sorted((a,b)))
        if key in seen:continue
        seen.add(key);p,q=net['nodes'][a],net['nodes'][b]
        spur=any(tuple(round(v,7) for v in x) in stalls for x in (p,q))
        x,y=pixel(p),pixel(q)
        ax.plot([x[0],y[0]],[x[1],y[1]],color='#00e5ff' if not spur else '#ffe2a2',linewidth=1.2 if not spur else .45,alpha=.9)
    ax.plot([],[],color='#00e5ff',label='Corrected estimated road / aisle centre')
    ax.plot([],[],color='#ffbd42',label='Unchanged estimated parking bays')
    ax.set_xlim(290,1400);ax.set_ylim(1180,65);ax.axis('off')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.01),frameon=False,ncol=1)
    fig.text(.13,.015,'Source imagery: Esri and imagery providers. Geometry remains estimated, not surveyed.',fontsize=10)
    out=ROOT/'research/vehicle_clearance_20261105'
    for suffix in ('png','pdf'):fig.savefig(out/f'downtown_corrected_roads.{suffix}',dpi=220,bbox_inches='tight')
    plt.close(fig)

if __name__=='__main__':main()
