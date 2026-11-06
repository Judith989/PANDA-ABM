"""Small geometry predicates shared by pedestrian validation and crossing safety."""
import math

def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def point_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];n=dx*dx+dy*dy
    t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/n)) if n else 0.
    return math.dist(p,(a[0]+t*dx,a[1]+t*dy))
def segments_intersect(a,b,c,d):
    if max(a[0],b[0])+1e-8<min(c[0],d[0]) or max(c[0],d[0])+1e-8<min(a[0],b[0]) or max(a[1],b[1])+1e-8<min(c[1],d[1]) or max(c[1],d[1])+1e-8<min(a[1],b[1]):return False
    return cross(a,b,c)*cross(a,b,d)<=1e-10 and cross(c,d,a)*cross(c,d,b)<=1e-10

def segment_distance(a,b,c,d):
    return 0. if segments_intersect(a,b,c,d) else min(point_segment(a,c,d),point_segment(b,c,d),point_segment(c,a,b),point_segment(d,a,b))
def inside(p,poly):
    found=False
    for a,b in zip(poly,poly[1:]+poly[:1]):
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:found=not found
    return found

def segment_hits_polygon(a,b,poly):
    return inside(a,poly) or inside(b,poly) or any(segments_intersect(a,b,c,d) for c,d in zip(poly,poly[1:]+poly[:1]))
def bay_polygon(slot):
    angle=math.radians(slot.get('heading_deg',0));angle=math.pi/2-angle if slot.get('heading_reference')=='clockwise_from_north' else angle
    u=(math.cos(angle),math.sin(angle));v=(-u[1],u[0]);l=slot.get('length_m',4.9)/2;w=slot.get('width_m',2.06)/2;x,y=slot['local_x_m'],slot['local_y_m']
    return [(x+i*l*u[0]+j*w*v[0],y+i*l*u[1]+j*w*v[1]) for i,j in [(-1,-1),(-1,1),(1,1),(1,-1)]]

class ObstacleIndex:
    def __init__(self,polygons):
        self.polygons=dict(polygons);self.cells={}
        for key,poly in polygons:
            for x in range(math.floor(min(p[0] for p in poly)/10),math.floor(max(p[0] for p in poly)/10)+1):
                for y in range(math.floor(min(p[1] for p in poly)/10),math.floor(max(p[1] for p in poly)/10)+1):self.cells.setdefault((x,y),set()).add(key)
    def hits(self,a,b,ignore=None):
        keys=set()
        for x in range(math.floor(min(a[0],b[0])/10),math.floor(max(a[0],b[0])/10)+1):
            for y in range(math.floor(min(a[1],b[1])/10),math.floor(max(a[1],b[1])/10)+1):keys.update(self.cells.get((x,y),()))
        return any(k!=ignore and segment_hits_polygon(a,b,self.polygons[k]) for k in keys)
