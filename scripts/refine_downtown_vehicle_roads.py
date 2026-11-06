"""Reproducible image-informed road-centre corrections; parking inventory unchanged.

The source image is the archived Esri mosaic. Corrections remain estimates, not
surveyed lanes. Save a candidate for review before replacing the active config.
"""
import json
import math
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    out=ROOT/'research/vehicle_clearance_20261105'
    source=out/'before_final_road_correction.json'
    if not source.exists():source=ROOT/'data/lot_config.downtown_laramie.json'
    raw = json.loads(source.read_text())
    net = raw['aisle_network']
    if net.get('geometry_revision'):
        raise ValueError('Use the preserved pre-correction source; do not apply offsets twice.')
    # Remove the earlier rectangular detour into the curb area. The corrected
    # street centre itself now clears these bays, so that detour is unnecessary.
    from panda_abm.environment.pedestrian_geometry import point_segment
    removed=set();replacements=[]
    for repair in net.get('clearance_repairs',[]):
        a,b=repair['original'];replacements.append([a,b])
        for key,point in net['nodes'].items():
            if key not in (a,b) and any(point_segment(point,p,q)<1e-5 for p,q in zip(repair['route'],repair['route'][1:])):
                removed.add(key)
        for access in net['space_access'].values():
            if access['node'] in removed:access['node']=a
    net['edges']=[e for e in net['edges'] if not any(k in removed for k in e)]+replacements
    for key in removed:net['nodes'].pop(key,None)
    net['clearance_repairs']=[]
    original = {k: tuple(v) for k, v in net['nodes'].items()}
    info = json.loads((ROOT/'research/downtown_review/20261105/imagery.json').read_text())
    def local(p):
        x, y = p; n = 2**info['zoom']
        lon = (info['tile_x0']+x/256)/n*360-180
        lat = math.degrees(math.atan(math.sinh(math.pi*(1-2*(info['tile_y0']+y/256)/n))))
        return [(lon-raw['meta']['ref_lon'])*111000*math.cos(math.radians(raw['meta']['ref_lat'])),
                (lat-raw['meta']['ref_lat'])*111000]
    def projection(point, p, q):
        d = [q[i]-p[i] for i in range(2)]; l2=sum(v*v for v in d)
        t=sum((point[i]-p[i])*d[i] for i in range(2))/l2
        foot=[p[i]+t*d[i] for i in range(2)]
        return t, foot, math.dist(point, foot)
    # Positive offsets are to the left looking from the named aisle's first end.
    shifts = {'cross_0_0': .7, 'cross_1_0': 2.8, 'cross_2_0': 1.65,
              'cross_2_1': .3, 'street_0_0': .55, 'street_0_1': -2.95,
              'street_1_1': .55}
    stall_points = {(round(s['local_x_m'],7),round(s['local_y_m'],7)) for s in raw['slots']}
    lot_lines = {'lot_north': (local((380,791)),local((550,811))),
                 'lot_south': (local((380,917.3)),local((540,945.6)))}
    changes=[]
    for name,(a,b) in net['aisles'].items():
        p,q=original[a],original[b];length=math.dist(p,q)
        normal=(-(q[1]-p[1])/length,(q[0]-p[0])/length)
        for key, point in original.items():
            if tuple(round(x,7) for x in point) in stall_points: continue
            t,foot,distance=projection(point,p,q)
            if distance>1e-4 or not -1e-7<=t<=1+1e-7: continue
            if name in lot_lines:
                x,y=lot_lines[name];new=[x[i]+t*(y[i]-x[i]) for i in range(2)]
            else:
                offset=shifts.get(name,0)*min(1.,max(0.,t*length/12),max(0.,(1-t)*length/12))
                new=[point[i]+offset*normal[i] for i in range(2)]
            if math.dist(point,new)>1e-7:
                net['nodes'][key]=new;changes.append(dict(node=key,aisle=name,before=point,after=new))
    # The image shows entry at the north-west driveway, not through the occupied
    # parallel curb row at the level of each internal parking aisle.
    lot_starts=[net['aisles'][k][0] for k in lot_lines]
    for start in lot_starts:
        own=next(k for k in lot_lines if net['aisles'][k][0]==start)
        p,q=[original[k] for k in net['aisles'][own]]
        def keep(edge):
            if start not in edge:return True
            other=edge[1] if edge[0]==start else edge[0]
            t,_,d=projection(original[other],p,q)
            return d<1e-4 and t>1e-5
        net['edges']=[e for e in net['edges'] if keep(e)]
    # Find and split the existing directed street edge nearest the entrance.
    desired=local((345,735));candidates=[]
    for a,b in net['edges']:
        if a in lot_starts or b in lot_starts:continue
        p,q=net['nodes'][a],net['nodes'][b]
        if math.dist(p,q)<1e-8:continue
        t,foot,d=projection(desired,p,q)
        if 0<t<1:candidates.append((d,a,b,foot))
    _,a,b,foot=min(candidates)
    key='reviewed_north_driveway_street';net['nodes'][key]=foot
    edges=[]
    for x,y in net['edges']:
        if (x,y) in ((a,b),(b,a)):edges.extend([[x,key],[key,y]])
        else:edges.append([x,y])
    top='reviewed_north_driveway_lot';net['nodes'][top]=local((380,735))
    for x,y in ((key,top),(top,lot_starts[0]),(lot_starts[0],lot_starts[1])):
        edges.extend([[x,y],[y,x]])
    net['edges']=edges
    net['geometry_revision']={'source':'archived Esri mosaic; estimated lane-centre correction',
        'street_offsets_m':shifts,'lot_aisle_pixels':{'north':[[380,791],[550,811]],'south':[[380,917.3],[540,945.6]]},
        'parking_centres_changed':False,'surveyed':False}
    (out/'downtown_roads_candidate.json').write_text(json.dumps(raw,separators=(',',':'))+'\n')
    (out/'downtown_road_changes.json').write_text(json.dumps(changes,indent=2)+'\n')
    print('Candidate saved;',len(changes),'node adjustments. Active configuration unchanged.')

if __name__=='__main__':main()
