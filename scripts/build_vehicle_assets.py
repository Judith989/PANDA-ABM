"""Build lightweight original vehicle meshes for the Cesium display (metres)."""
import json
import math
import struct
from pathlib import Path

VEHICLES={'compact':(3.9,1.72,1.48),'sedan':(4.55,1.82,1.46),'suv':(4.75,1.94,1.78),'van':(5.15,2.0,2.05),'truck':(5.45,2.02,1.85)}
COLORS={'compact':[.05,.52,.59,1],'sedan':[.06,.25,.56,1],'suv':[.72,.14,.09,1],'van':[.8,.83,.82,1],'truck':[.25,.29,.32,1]}


def vehicle_glb(kind):
    length,width,height=VEHICLES[kind];vertices=[];indices=[];parts=[]
    def mesh(points,faces,material):
        start=len(vertices)//3;first=len(indices)
        # glTF Y-up, +Z vehicle front; Cesium's standard model-axis conversion.
        for x,y,z in points:vertices.extend([-y,z,x])
        for a,b,c in faces:indices.extend([start+a,start+b,start+c])
        parts.append((first,len(indices)-first,material))
    def prism(profile,y0,y1,material):
        n=len(profile);points=[(x,y,z) for y in (y0,y1) for x,z in profile];faces=[]
        for i in range(1,n-1):faces.extend([(0,i+1,i),(n,n+i,n+i+1)])
        for i in range(n):j=(i+1)%n;faces.extend([(i,j,n+j),(i,n+j,n+i)])
        mesh(points,faces,material)
    def box(x0,x1,y0,y1,z0,z1,material):prism([(x0,z0),(x1,z0),(x1,z1),(x0,z1)],y0,y1,material)
    l=length/2;w=width/2;wheel=.32 if kind not in ('van','truck') else .37
    prism([(-l,.35),(l-.10,.35),(l,.55),(l-.10,.85),(-l+.08,.85),(-l,.62)],-w,w,0)
    rear=-l*.64;front=l*.45;roof=height-.05
    if kind=='van':rear=-l*.87;front=l*.65
    if kind=='truck':rear=-l*.06;front=l*.56
    profile=[(rear,.84),(front,.84),(front-.28,roof-.10),(rear+.26,roof)]
    prism(profile,-w*.88,w*.88,0)
    # Dark side glazing and front/rear glass, separated from body panels.
    for sign in (-1,1):
        y=sign*w*.892
        for a,b in ((rear+.11,(rear+front)/2-.035),((rear+front)/2+.035,front-.12)):
            prism([(a,1.02),(b,1.02),(b-.14,roof-.17),(a+.13,roof-.12)],y-.006,y+.006,1)
    mesh([(front+.005,-w*.76,.99),(front+.005,w*.76,.99),(front-.265,w*.76,roof-.18),(front-.265,-w*.76,roof-.18)],[(0,1,2),(0,2,3)],1)
    mesh([(rear-.005,-w*.73,1.0),(rear-.005,w*.73,1.0),(rear+.245,w*.73,roof-.12),(rear+.245,-w*.73,roof-.12)],[(0,1,2),(0,2,3)],1)
    if kind=='truck':
        box(-l+.12,rear-.05,-w*.81,w*.81,.86,.91,2)
        box(-l+.05,rear-.05,-w,-w+.13,.84,1.17,0);box(-l+.05,rear-.05,w-.13,w,.84,1.17,0)
    # Tires and exposed silver wheel hubs; 16-sided cylinders around lateral axis.
    for x in (-l*.63,l*.63):
        for sign in (-1,1):
            for radius,y0,y1,material in ((wheel,sign*(w-.13),sign*(w+.055),2),(wheel*.54,sign*(w+.06),sign*(w+.067),3)):
                points=[(x+radius*math.cos(i*math.tau/16),y,wheel+radius*math.sin(i*math.tau/16)) for y in (y0,y1) for i in range(16)]
                faces=[]
                for i in range(16):j=(i+1)%16;faces.extend([(i,j,16+j),(i,16+j,16+i)])
                for i in range(1,15):faces.extend([(0,i,i+1),(16,16+i+1,16+i)])
                mesh(points,faces,material)
    for y in (-w*.68,w*.68):
        box(l-.045,l+.015,y-.16,y+.16,.57,.73,4)
        box(-l-.01,-l+.04,y-.16,y+.16,.57,.76,5)
    box(l-.025,l+.025,-w*.33,w*.33,.43,.56,2)
    positions=struct.pack('<'+'f'*len(vertices),*vertices);elements=struct.pack('<'+'H'*len(indices),*indices)
    binary=positions+elements;binary+=b'\0'*((-len(binary))%4)
    materials=[dict(doubleSided=True,pbrMetallicRoughness=dict(baseColorFactor=c,metallicFactor=.18 if i==0 else .0,roughnessFactor=.35 if i==0 else .65)) for i,c in enumerate([COLORS[kind],[.06,.13,.18,1],[.025,.028,.03,1],[.58,.62,.64,1],[1,.95,.67,1],[.8,.025,.02,1]])]
    accessors=[dict(bufferView=0,componentType=5126,count=len(vertices)//3,type='VEC3',min=[min(vertices[i::3]) for i in range(3)],max=[max(vertices[i::3]) for i in range(3)])]
    primitives=[]
    for first,count,material in parts:
        accessor=len(accessors);accessors.append(dict(bufferView=1,byteOffset=first*2,componentType=5123,count=count,type='SCALAR'))
        primitives.append(dict(attributes=dict(POSITION=0),indices=accessor,material=material))
    gltf=dict(asset=dict(version='2.0',generator='PANDA original vehicle visual'),scene=0,scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],meshes=[dict(primitives=primitives)],materials=materials,buffers=[dict(byteLength=len(binary))],bufferViews=[dict(buffer=0,byteOffset=0,byteLength=len(positions),target=34962),dict(buffer=0,byteOffset=len(positions),byteLength=len(elements),target=34963)],accessors=accessors)
    data=json.dumps(gltf,separators=(',',':')).encode();data+=b' '*((-len(data))%4)
    return struct.pack('<III',0x46546c67,2,12+8+len(data)+8+len(binary))+struct.pack('<II',len(data),0x4e4f534a)+data+struct.pack('<II',len(binary),0x004e4942)+binary


def build(destination):
    destination=Path(destination);destination.mkdir(exist_ok=True,parents=True)
    for kind in VEHICLES:(destination/(kind+'.glb')).write_bytes(vehicle_glb(kind))

if __name__=='__main__':build(Path(__file__).resolve().parents[1]/'dashboard/assets/vehicles')
