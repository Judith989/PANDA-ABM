"""Prepare local GLB assets and a measured similarity fit to corrected slots."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import struct
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def read_glb(path):
    b=path.read_bytes()
    size=struct.unpack_from('<I',b,12)[0]
    g=json.loads(b[20:20+size])
    start=20+size
    n=struct.unpack_from('<I',b,start)[0]
    return g,b[start+8:start+8+n]


def node_center(g,node):
    a=g['accessors'][g['meshes'][node['mesh']]['primitives'][0]['attributes']['POSITION']]
    p=(np.array(a['min'])+a['max'])/2
    x,y,z,w=node.get('rotation',[0,0,0,1])
    r=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    p=r@(p*np.array(node.get('scale',[1,1,1])))+node.get('translation',[0,0,0])
    return np.array([p[0],-p[2]])


def optimize(source,dest,building=False):
    g,b=read_glb(source)
    if building:
        # The satellite/highway mesh in this export is unrelated display context.
        g['nodes']=[g['nodes'][0]]
        g['scenes']=[{'nodes':[0]}];g['scene']=0
    images={im['bufferView']:im for im in g.get('images',[]) if 'bufferView' in im}
    chunks=[];offset=0
    for i,v in enumerate(g['bufferViews']):
        content=b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
        if i in images:
            image=Image.open(io.BytesIO(content)).convert('RGB')
            image.thumbnail((2048,2048))
            buf=io.BytesIO();image.save(buf,format='JPEG',quality=85)
            content=buf.getvalue();images[i]['mimeType']='image/jpeg'
        v['byteOffset']=offset;v['byteLength']=len(content)
        content+=b'\0'*((-len(content))%4)
        chunks.append(content);offset+=len(content)
    payload=b''.join(chunks);g['buffers']=[{'byteLength':len(payload)}]
    doc=json.dumps(g,separators=(',',':')).encode();doc+=b' '*((-len(doc))%4)
    dest.write_bytes(struct.pack('<III',0x46546c67,2,12+8+len(doc)+8+len(payload))+
                     struct.pack('<II',len(doc),0x4e4f534a)+doc+struct.pack('<II',len(payload),0x004e4942)+payload)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    args=parser.parse_args()
    out=ROOT/'dashboard/assets';out.mkdir(parents=True,exist_ok=True)
    config=json.loads((ROOT/'data/lot_config.json').read_text())
    slots={s['id']:s for s in config['slots']}
    g,_=read_glb(args.source/'parking_spots.glb')
    pairs=[(n,node_center(g,n)) for n in g['nodes'] if n.get('name') in slots]
    x=np.array([p for n,p in pairs]);y=np.array([[slots[n['name']]['local_x_m'],slots[n['name']]['local_y_m']] for n,p in pairs])
    xc=x.mean(0);yc=y.mean(0)
    u,s,vt=np.linalg.svd((x-xc).T@(y-yc));rotation=u@vt
    if np.linalg.det(rotation)<0:raise ValueError('Reflection is not a valid scene rotation')
    scale=s.sum()/((x-xc)**2).sum();offset=yc-scale*xc@rotation
    residual=np.linalg.norm(scale*x@rotation+offset-y,axis=1)
    for name in ['walmart_building.glb','parking_asphalt.glb']:
        optimize(args.source/name,out/name,building=name.startswith('walmart'))
    fit=dict(matched_ids=len(pairs),scale=float(scale),rotation_radians=float(np.arctan2(rotation[0,1],rotation[0,0])),
             east_m=float(offset[0]),north_m=float(offset[1]),height_m=0,
             fit_rmse_m=float(np.sqrt(np.mean(residual**2))),max_residual_m=float(residual.max()),
             slot_placement='Corrected JSON coordinates; legacy slot meshes are not rendered.',
             cesium_axes=dict(up='Y',forward='X',mapping='glTF x,y,z -> ENU x,-z,y; disable Z-forward adaptation'),
             note='Least-squares scene fit to all matched centres. Building and pavement remain approximate; simulation geometry is unchanged.',
             config_sha256=hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest(),
             source_sha256={n:hashlib.sha256((args.source/n).read_bytes()).hexdigest() for n in ['parking_spots.glb','walmart_building.glb','parking_asphalt.glb']},
             asset_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.glb')})
    (ROOT/'dashboard/alignment.json').write_text(json.dumps(fit,indent=2)+'\n')
    print(json.dumps({k:fit[k] for k in ['matched_ids','scale','fit_rmse_m','max_residual_m']},indent=2))


if __name__=='__main__':main()
