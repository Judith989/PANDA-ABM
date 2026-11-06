"""Create lightweight building-context GLB from attributed OSM footprints.
Heights without mapped values are explicit illustrative assumptions.
"""
from pathlib import Path
import json,math,struct,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT))
OUT=ROOT/'research/downtown_review/20261105'

def triangulate(poly):
    cross=lambda a,b,c:(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    order=list(range(len(poly)))
    if sum(poly[i][0]*poly[(i+1)%len(poly)][1]-poly[(i+1)%len(poly)][0]*poly[i][1] for i in range(len(poly)))<0:order.reverse()
    faces=[]
    while len(order)>3:
        for j,b in enumerate(order):
            a,c=order[j-1],order[(j+1)%len(order)]
            if cross(poly[a],poly[b],poly[c])<=1e-8:continue
            if any(min(cross(poly[a],poly[b],poly[k]),cross(poly[b],poly[c],poly[k]),cross(poly[c],poly[a],poly[k]))>=-1e-8 for k in order if k not in (a,b,c)):continue
            faces.append((a,b,c));order.pop(j);break
        else:raise ValueError('Footprint requires geometry repair')
    faces.append(tuple(order));return faces

def build():
    from panda_abm.twin.environments import validate_environment
    env=json.loads((OUT/'environment.review.json').read_text(encoding='utf8'));cfg=env['config'];meta=cfg['meta'];lat,lon=meta['ref_lat'],meta['ref_lon']
    local=lambda xy:((xy[0]-lon)*111000*math.cos(math.radians(lat)),(xy[1]-lat)*111000)
    root=ET.parse(OUT/'osm_network.osm').getroot();coords={n.get('id'):(float(n.get('lon')),float(n.get('lat'))) for n in root.findall('node')}
    footprints=[];vertices=[];indices=[];skipped=[]
    for way in root.findall('way'):
        tags={t.get('k'):t.get('v') for t in way.findall('tag')};refs=[r.get('ref') for r in way.findall('nd')]
        if not tags.get('building') or len(refs)<4 or refs[0]!=refs[-1]:continue
        xy=[coords[r] for r in refs[:-1]];cx=sum(p[0] for p in xy)/len(xy);cy=sum(p[1] for p in xy)/len(xy)
        if not (-105.5964<cx<-105.59345 and 41.31005<cy<41.31223):continue
        poly=[local(p) for p in xy]
        # Drop repeated or collinear vertices before roof triangulation.
        clean=[]
        for p in poly:
            if not clean or math.dist(p,clean[-1])>0.03:clean.append(p)
        poly=clean
        try:faces=triangulate(poly)
        except ValueError:skipped.append(way.get('id'));continue
        height=6.;height_source='assumed_6m_for_visualization'
        try:
            if 'height' in tags:height=float(tags['height'].replace(' m',''));height_source='OSM_height_tag_not_survey_verified'
            elif 'building:levels' in tags:height=float(tags['building:levels'])*3.;height_source='OSM_levels_times_assumed_3m'
        except ValueError:pass
        height=max(2.,min(40.,height));base=len(vertices);count=len(poly)
        vertices.extend((x,y,z) for z in (0.,height) for x,y in poly)
        indices.extend(base+count+j for face in faces for j in face)
        for j in range(count):
            k=(j+1)%count;indices.extend([base+j,base+k,base+count+k,base+j,base+count+k,base+count+j])
        footprints.append(dict(id='osm_way_'+way.get('id'),name=tags.get('name'),footprint_m=poly,height_m=height,height_source=height_source))
    points=[v for p in vertices for v in p];blob=struct.pack('<'+'f'*len(points),*points);offset=len(blob);blob+=struct.pack('<'+'I'*len(indices),*indices)
    doc=dict(asset=dict(version='2.0',generator='PANDA OSM building context; illustrative heights',copyright='OpenStreetMap contributors, ODbL'),scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],meshes=[dict(primitives=[dict(attributes=dict(POSITION=0),indices=1,material=0)])],materials=[dict(name='Building context',doubleSided=True,pbrMetallicRoughness=dict(baseColorFactor=[.64,.59,.49,1],metallicFactor=0,roughnessFactor=.95))],buffers=[dict(byteLength=len(blob))],bufferViews=[dict(buffer=0,byteOffset=0,byteLength=offset,target=34962),dict(buffer=0,byteOffset=offset,byteLength=len(blob)-offset,target=34963)],accessors=[dict(bufferView=0,componentType=5126,count=len(vertices),type='VEC3',min=[min(v[i] for v in vertices) for i in range(3)],max=[max(v[i] for v in vertices) for i in range(3)]),dict(bufferView=1,componentType=5125,count=len(indices),type='SCALAR')])
    raw=json.dumps(doc,separators=(',',':')).encode();raw+=b' '*((-len(raw))%4);blob+=b'\0'*((-len(blob))%4)
    glb=struct.pack('<III',0x46546c67,2,12+8+len(raw)+8+len(blob))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',len(blob),0x004e4942)+blob
    asset=ROOT/'dashboard/assets/downtown_buildings.glb';asset.write_bytes(glb);(OUT/'downtown_buildings.glb').write_bytes(glb)
    cfg['buildings']=footprints
    net=cfg['aisle_network'];old_edges=list(net['edges']);nodes=net['nodes'];net['directed']=True
    # First Street between Ivinson and Garfield is tagged southbound in the reference OSM extract.
    # All other included roads retain bidirectional hypotheses where oneway is unspecified.
    one_way=[];edges=[]
    # Identify original First Street subsegments from their straight-line alignment.
    info=json.loads((OUT/'imagery.json').read_text(encoding='utf8'));n=2**info['zoom']
    def pixel_local(x,y):
        lon2=(info['tile_x0']+x/256)/n*360-180;lat2=math.degrees(math.atan(math.sinh(math.pi*(1-2*(info['tile_y0']+y/256)/n))))
        return local((lon2,lat2))
    first=[pixel_local(390,135),pixel_local(357,610),pixel_local(322,1090)]
    def on_segment(p,a,b):
        dx,dy=b[0]-a[0],b[1]-a[1];t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)
        return -.001<=t<=1.001 and math.dist(p,(a[0]+t*dx,a[1]+t*dy))<.03
    for a,b in old_edges:
        if math.dist(nodes[a],nodes[b])>1 and any(on_segment(nodes[a],u,v) and on_segment(nodes[b],u,v) for u,v in zip(first,first[1:])):
            south,north=(a,b) if nodes[a][1]<nodes[b][1] else (b,a);edges.append([north,south]);one_way.append([north,south])
        else:edges.extend([[a,b],[b,a]])
    net['edges']=list(map(list,dict.fromkeys(map(tuple,edges))))
    controls=[]
    for node in root.findall('node'):
        tags={t.get('k'):t.get('v') for t in node.findall('tag')}
        if tags.get('highway')!='traffic_signals':continue
        p=local(coords[node.get('id')]);key=min(nodes,key=lambda k:math.dist(p,nodes[k]))
        if math.dist(p,nodes[key])>8:continue
        if any(c['node']==key for c in controls):continue
        controls.append(dict(node=key,type='signal',cycle_s=96,offset_s=0,east_west_green=[0,42],north_south_green=[48,90],source_osm_node=node.get('id'),timing_status='assumed_fixed_cycle_not_observed',location_status='OSM_signal_snapped_to_draft_graph_within_8m'))
    net['controls']=controls
    meta.update(rule_policy='Require planned activity plus outbound and return walks to fit the time limit; no fines, enforcement or overstay model.',building_context='OSM footprints extruded for visualization; heights assumed unless tagged; not collision or pedestrian obstacles',traffic_status='Directed draft: OSM-tagged southbound First Street; other streets bidirectional hypotheses. Mapped signals use assumed cycles. No field validation.',rule_review_status='District-level parking guidance only; signs, loading and accessible designations require review',osm_source_url='https://www.openstreetmap.org/api/0.6/map?bbox=-105.5966,41.3099,-105.5934,41.3124',osm_sha256=hashlib.sha256((OUT/'osm_network.osm').read_bytes()).hexdigest(),osm_attribution='OpenStreetMap contributors; ODbL; retrieved 2026-11-05')
    env['alignment']=dict(east_m=0,north_m=0,height_m=0,rotation_radians=0,scale=1,up_axis='Z',forward_axis='X',context_note=meta['building_context'])
    env['model_files']=[dict(name='downtown_buildings.glb',sha256=hashlib.sha256(glb).hexdigest())]
    env=validate_environment(env)
    (OUT/'environment.review.json').write_text(json.dumps(env,indent=2)+'\n',encoding='utf8');(ROOT/'data/lot_config.downtown_laramie.review.json').write_text(json.dumps(env['config'],indent=2)+'\n',encoding='utf8')
    platform_config=json.loads(json.dumps(env['config']))
    platform_config['meta'].update(lot_name='Downtown Laramie',review_required=False,simulation_ready=True,platform_status='Selectable experimental environment; estimated geometry and assumed traffic settings')
    (ROOT/'data/lot_config.downtown_laramie.json').write_text(json.dumps(platform_config,indent=2)+'\n',encoding='utf8')
    report=dict(buildings=len(footprints),skipped_building_ids=skipped,vertices=len(vertices),triangles=len(indices)//3,model_bytes=len(glb),one_way_edges=len(one_way),signals=len(controls),model_sha256=hashlib.sha256(glb).hexdigest(),review_required=True)
    (OUT/'building_network_review.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    # Portable static 3D context review, independent of browser permissions.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    fig=plt.figure(figsize=(13,9));ax=fig.add_subplot(projection='3d')
    for b in footprints:
        poly=b['footprint_m'];h=b['height_m'];faces=[[(x,y,h) for x,y in poly]]
        for i,(x,y) in enumerate(poly):xx,yy=poly[(i+1)%len(poly)];faces.append([(x,y,0),(xx,yy,0),(xx,yy,h),(x,y,h)])
        ax.add_collection3d(Poly3DCollection(faces,facecolors='#aaa18b',edgecolors='#625c50',linewidths=.25,alpha=.98))
    for a,b in old_edges:ax.plot(*zip((*nodes[a],.1),(*nodes[b],.1)),color='#219fa7',lw=.8)
    for kind,color in [('on_street','#d87500'),('off_street','#247944')]:
        ss=[s for s in cfg['slots'] if s['parking_kind']==kind];ax.scatter([s['local_x_m'] for s in ss],[s['local_y_m'] for s in ss],[.2]*len(ss),s=7,color=color)
    for i,d in enumerate(cfg['destinations'],1):ax.text(d['local_x_m'],d['local_y_m'],10,str(i),fontweight='bold')
    ax.set_xlim(-140,140);ax.set_ylim(-125,140);ax.set_zlim(0,35);ax.set_box_aspect((1,1,.15));ax.view_init(elev=50,azim=-70);ax.set_axis_off()
    fig.text(.12,.04,'Illustrative building heights; OSM footprints and provisional parking geometry.\nBuilding shapes provide visual context only. © OpenStreetMap contributors.',fontsize=12)
    fig.savefig(OUT/'downtown_3d_review.png',dpi=180,bbox_inches='tight');plt.close(fig)
    # Add direction and control layers to the portable satellite review.
    def pixel(p):
        lat2=lat+p[1]/111000;lon2=lon+p[0]/(111000*math.cos(math.radians(lat)))
        return ((lon2+180)/360*n*256-info['tile_x0']*256,(1-math.asinh(math.tan(math.radians(lat2)))/math.pi)/2*n*256-info['tile_y0']*256)
    marks=['<!--urban-controls--><g id="urban-controls"><defs><marker id="direction" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#f542a4"/></marker></defs>']
    for a,b in one_way:
        x1,y1=pixel(nodes[a]);x2,y2=pixel(nodes[b]);marks.append(f'<path d="M {x1} {y1} L {x2} {y2}" stroke="#f542a4" stroke-width="2" marker-end="url(#direction)"/>')
    for c in controls:
        x,y=pixel(nodes[c['node']]);marks.append(f'<rect x="{x-8}" y="{y-8}" width="16" height="16" fill="#f542a4" stroke="black"><title>Mapped signal; assumed 96-second cycle</title></rect>')
    marks.append('</g><!--/urban-controls-->')
    html_path=OUT/'layout_review.html';text=html_path.read_text(encoding='utf8')
    import re
    text=re.sub(r'<!--urban-controls-->.*?<!--/urban-controls-->','',text,flags=re.S)
    text=text.replace('</svg>', ''.join(marks)+'</svg>').replace('<b>Layers</b>','<b>Layers</b><p>Pink arrows: mapped one-way direction. Pink squares: mapped signals with assumed timings.</p>') if 'Pink arrows:' not in text else text.replace('</svg>',''.join(marks)+'</svg>')
    html_path.write_text(text,encoding='utf8')
    print(json.dumps(report))

if __name__=='__main__':build()
