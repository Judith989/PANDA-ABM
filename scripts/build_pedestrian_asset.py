"""Original articulated pedestrian mesh, with named limbs driven by simulation time."""
from pathlib import Path
import json
import math
import struct


def build(destination):
    data=bytearray();views=[];accessors=[];meshes=[];nodes=[]
    def accessor(values,kind,components):
        while len(data)%4:data.append(0)
        offset=len(data);flat=[v for row in values for v in row] if components>1 else values
        code='f' if kind==5126 else 'H';data.extend(struct.pack('<'+code*len(flat),*flat))
        view=len(views);views.append(dict(buffer=0,byteOffset=offset,byteLength=len(data)-offset))
        a=dict(bufferView=view,componentType=kind,count=len(values),type='VEC3' if components==3 else 'SCALAR')
        if components==3:a.update(min=[min(row[i] for row in values) for i in range(3)],max=[max(row[i] for row in values) for i in range(3)])
        index=len(accessors);accessors.append(a);return index
    def cuboid(size,centre,material):
        x,y,z=size;cx,cy,cz=centre
        points=[(cx+dx*x/2,cy+dy*y/2,cz+dz*z/2) for dx,dy,dz in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        indices=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,3,7,6,3,6,2,0,4,7,0,7,3,1,2,6,1,6,5]
        meshes.append(dict(primitives=[dict(attributes=dict(POSITION=accessor(points,5126,3)),indices=accessor(indices,5123,1),material=material)]));return len(meshes)-1
    torso=cuboid((.44,.5,.25),(0,1.12,0),0)
    head=cuboid((.24,.28,.24),(0,1.53,.015),1)
    neck=cuboid((.13,.12,.13),(0,1.36,0),1)
    roots=[]
    for name,mesh in [('Torso',torso),('Head',head),('Neck',neck)]:roots.append(len(nodes));nodes.append(dict(name=name,mesh=mesh))
    for name,x,material,size,centre,y in [('LeftArm',-.29,0,(.12,.53,.13),(0,-.24,0),1.34),('RightArm',.29,0,(.12,.53,.13),(0,-.24,0),1.34),('LeftLeg',-.115,2,(.16,.86,.18),(0,-.43,0),.89),('RightLeg',.115,2,(.16,.86,.18),(0,-.43,0),.89)]:
        mesh=cuboid(size,centre,material);roots.append(len(nodes));nodes.append(dict(name=name,translation=[x,y,0],mesh=mesh))
    materials=[dict(doubleSided=True,pbrMetallicRoughness=dict(baseColorFactor=c,metallicFactor=0,roughnessFactor=.9)) for c in ([.95,.4,.08,1],[.64,.39,.24,1],[.08,.15,.27,1])]
    while len(data)%4:data.append(0)
    g=dict(asset=dict(version='2.0',generator='PANDA original pedestrian'),scene=0,scenes=[dict(nodes=roots)],nodes=nodes,meshes=meshes,materials=materials,buffers=[dict(byteLength=len(data))],bufferViews=views,accessors=accessors)
    text=json.dumps(g,separators=(',',':')).encode();text+=b' '*((-len(text))%4)
    output=struct.pack('<III',0x46546c67,2,12+8+len(text)+8+len(data))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(data),0x004e4942)+data
    path=Path(destination);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(output)

if __name__=='__main__':build(Path(__file__).resolve().parents[1]/'dashboard/assets/pedestrian.glb')
