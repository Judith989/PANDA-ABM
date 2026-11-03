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
SOURCE=ASSETS/'walmart_satellite_source.jpg'
ANCHOR_A=(-105.541668,41.303614)
ANCHOR_B=(-105.537377,41.301196)


def pixel(lon,lat):
    def mercator(value):return math.log(math.tan(math.pi/4+math.radians(value)/2))
    return (550+(lon-ANCHOR_A[0])*400/(ANCHOR_B[0]-ANCHOR_A[0]),
            250+(mercator(lat)-mercator(ANCHOR_A[1]))*300/(mercator(ANCHOR_B[1])-mercator(ANCHOR_A[1])))


def main():
    config=json.loads((ROOT/'data/lot_config.json').read_text())
    photo=np.asarray(Image.open(SOURCE).convert('RGB'))
    assert photo.shape[:2]==(720,1280),'Geographic anchors require the original screenshot'
    fig=plt.figure(figsize=(8.5,8.5),facecolor='white')
    ax=fig.add_axes([.035,.17,.93,.76])
    ax.imshow(photo)
    ax.set_xlim(520,950);ax.set_ylim(590,200);ax.set_aspect('equal');ax.set_axis_off()
    positions={'door_1':(565,477),'door_2':(747,492),'exit_a':(625,214),'exit_b':(929,377)}
    records=[]
    for group,color in (('walmart_doors','#087eab'),('parking_lot_exits','#edb925')):
        for point in config[group]:
            x,y=pixel(point['lon'],point['lat']);key=point['id'];door=key.startswith('door')
            short=('D'+key[-1]) if door else key[-1].upper()
            label={'door_1':'Door 1 (west)','door_2':'Door 2 (east)','exit_a':'Entry/Exit A (north)','exit_b':'Entry/Exit B (east)'}[key]
            ax.scatter(x,y,s=350,c=color,edgecolors='white',linewidths=2,zorder=5)
            ax.text(x,y,short,ha='center',va='center',color='white' if door else '#14212b',weight='bold',fontsize=11,zorder=6)
            annotation=ax.annotate(label,xy=(x,y),xytext=positions[key],ha='right' if key=='exit_b' else 'center',
                va='center',fontsize=10,weight='bold',color='#14212b',zorder=7,
                bbox=dict(boxstyle='round,pad=.4',fc='white',ec=color,lw=1.6),
                arrowprops=dict(arrowstyle='-',color=color,lw=2,shrinkB=13))
            annotation.arrow_patch.set_path_effects([pe.Stroke(linewidth=4,foreground='white'),pe.Normal()])
            records.append(dict(id=key,label=label,lat=point['lat'],lon=point['lon'],image_x=x,image_y=y))
    fig.suptitle('Walmart Supercenter — study locations',fontsize=17,weight='bold',y=.975)
    fig.text(.5,.94,'Laramie, Wyoming | North up | Estimated model locations',ha='center',fontsize=10,color='#475569')
    fig.text(.5,.137,'D1 / D2: Walmart doors     A / B: vehicle entry and exit',ha='center',fontsize=11)
    # Preserve the original map branding and attribution pixels beneath the
    # cropped study view; retain the full unchanged source alongside the figure.
    logo=fig.add_axes([.44,.091,.12,.035]);logo.imshow(photo[679:700,600:760]);logo.set_axis_off()
    credit=fig.add_axes([.02,.059,.96,.025]);credit.imshow(photo[705:720,460:1280]);credit.set_axis_off()
    fig.text(.5,.029,'Source: project-review Google Maps screenshot; configured points from data/lot_config.json.',
        ha='center',fontsize=8,color='#475569')
    fig.savefig(ASSETS/'walmart_doors_and_access.png',dpi=180);plt.close(fig)
    provenance=dict(source='Google Maps screenshot used in the earlier site review',
        source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        config_sha256=hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest(),
        image_size=[1280,720],projection='Mercator interpolation from two manually read screenshot anchors',
        anchors=[dict(lon=ANCHOR_A[0],lat=ANCHOR_A[1],pixel=[550,250]),dict(lon=ANCHOR_B[0],lat=ANCHOR_B[1],pixel=[950,550])],
        landmarks=records,note='Estimated alignment, not a survey. Source pixels are plotted with scientific annotations; no aerial content is generated.')
    (ASSETS/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(ASSETS/'walmart_doors_and_access.png')


if __name__=='__main__':main()
