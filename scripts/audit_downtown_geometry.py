"""Numbered audit using the exact compass-angle convention consumed by the dashboard."""
from pathlib import Path
import json,math,csv
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/downtown_geometry_audit_20261105'

def main():
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib.patches import Polygon,Rectangle
 from PIL import Image
 config=json.loads((ROOT/'data/lot_config.downtown_laramie.json').read_text(encoding='utf8'))
 image=Image.open(ROOT/'research/downtown_review/20261105/satellite.png')
 m_per_px=math.cos(math.radians(config['meta']['ref_lat']))*2*math.pi*6378137/(256*2**19)
 plt.rcParams.update({'font.size':12,'font.weight':'bold','pdf.fonttype':42})
 for name,bounds,size in [('numbered_layout',(285,1390,1190,50),(15,15)),('numbered_off_street',(310,600,1045,710),(9,10))]:
  fig,ax=plt.subplots(figsize=size);ax.imshow(image)
  for slot in config['slots']:
   x,y=slot['source_pixel']
   if not bounds[0]<=x<=bounds[1] or not bounds[3]<=y<=bounds[2]:continue
   a=math.radians(slot['heading_deg']);u=(math.sin(a),-math.cos(a));v=(math.cos(a),math.sin(a));l=slot['length_m']/m_per_px/2;w=slot['width_m']/m_per_px/2
   corners=[(x+i*l*u[0]+j*w*v[0],y+i*l*u[1]+j*w*v[1]) for i,j in [(-1,-1),(-1,1),(1,1),(1,-1)]]
   ax.add_patch(Polygon(corners,fill=False,edgecolor='#00f1ff',lw=.9))
   ax.text(x,y,slot['id'].replace('DT',''),ha='center',va='center',fontsize=6 if name=='numbered_layout' else 9,color='white',bbox=dict(facecolor='black',alpha=.7,pad=.15,edgecolor='none'))
  for i,area in enumerate(config['unresolved_parking_areas'],1):
   x0,y0,x1,y1=area['source_pixel_bounds'];ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor='#ff3555',lw=2,linestyle='--'))
   ax.text(x0,y0-3,f'U{i}: count unresolved',color='white',fontsize=8 if name=='numbered_layout' else 11,bbox=dict(facecolor='#a00020',alpha=.85,edgecolor='none',pad=1))
  ax.set_xlim(bounds[:2]);ax.set_ylim(bounds[2:]);ax.axis('off');fig.text(.08,.025,'Cyan: configured bays, numbered DT IDs. Red: incomplete or ambiguous parking arrangements.\nCounts remain provisional. Background: Esri and imagery providers.',fontsize=10)
  fig.savefig(OUT/(name+'.png'),dpi=220,bbox_inches='tight');fig.savefig(OUT/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
 svg=[]
 for slot in config['slots']:
  x,y=slot['source_pixel'];a=math.radians(slot['heading_deg']);u=(math.sin(a),-math.cos(a));v=(math.cos(a),math.sin(a));l=slot['length_m']/m_per_px/2;w=slot['width_m']/m_per_px/2
  pts=' '.join(f'{x+i*l*u[0]+j*w*v[0]},{y+i*l*u[1]+j*w*v[1]}' for i,j in [(-1,-1),(-1,1),(1,1),(1,-1)])
  svg.append(f'<polygon points="{pts}" fill="none" stroke="cyan"><title>{slot["id"]}: {slot["module"]}; {slot["heading_deg"]} degrees clockwise from north; count provisional</title></polygon><text class="ids" x="{x}" y="{y}" fill="white" stroke="black" stroke-width=".2" font-size="8" text-anchor="middle">{slot["id"]}</text>')
 for area in config['unresolved_parking_areas']:
  x,y,xx,yy=area['source_pixel_bounds'];svg.append(f'<rect x="{x}" y="{y}" width="{xx-x}" height="{yy-y}" stroke="red" stroke-width="2" fill="red" fill-opacity=".12"><title>{area["issue"]}</title></rect>')
 doc='<!doctype html><meta charset="utf-8"><title>Numbered downtown geometry audit</title><style>body{font:16px system-ui}svg{width:2000px}label{position:fixed;right:20px;top:10px;background:white;padding:12px}</style><h1>Numbered geometry audit</h1><p>Scroll to inspect the full-resolution bay overlay. Hover for bay IDs and row names. Red zones require additional inventory review.</p><label><input type="checkbox" checked onchange="document.querySelectorAll(\'.ids\').forEach(e=>e.style.display=this.checked?\'\':\'none\')">Show IDs</label><svg viewBox="280 40 1120 1160"><image href="../downtown_review/20261105/satellite.png" width="1536" height="1280"/>'+''.join(svg)+'</svg>'
 (OUT/'numbered_audit.html').write_text(doc,encoding='utf8')
 with (OUT/'all_spaces_audit.csv').open('w',encoding='utf8',newline='') as h:
  keys=['id','module','lat','lon','local_x_m','local_y_m','heading_deg','heading_reference','geometry_review_status'];w=csv.DictWriter(h,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(config['slots'])
 (OUT/'AUDIT.md').write_text('''# Downtown geometry audit

The original configuration and source generator were preserved under before/. The audit corrected a 90-degree reference mismatch between the downtown compass headings and the dashboard mathematical-angle convention. The display and parked vehicles now use the same conversion, while the Walmart convention remains unchanged. Seven horizontal street rows had their diagonal axes corrected after viewing the imagery.

The active inventory still contains 241 provisional centres, including 42 fitted off-street bays. The 42-space off-street figure is incomplete, not verified capacity. Three red areas identify additional/ambiguous arrangements. No extra legal bays were invented to force a total: car positions are not evidence of painted, permitted stalls. All configured row counts and all space coordinates are listed in CSV for inspection. Existing fitted coordinates were not individually surveyed or certified.

The higher-zoom imagery endpoint returned map-data-unavailable placeholders, not higher-resolution usable imagery. The publicly linked city ADA app was inaccessible through its public item endpoint. Neither supplied a definitive complete stall inventory. The user screenshots and the Esri mosaic can also differ in image date. Absolute completeness and exact coordinates cannot be certified from these sources; a clear orthophoto showing every stripe, an engineering parking plan, or an on-site inventory is needed.

This audit does not claim completion of the parking census. Numbered overlays are for locating specific errors and resolving unknown areas. Existing paper outputs were not rerun or relabeled as corrected results.
''',encoding='utf8')
 print('Saved numbered full-layout and lot-detail overlays, row audit and all-space CSV.')
if __name__=='__main__':main()
