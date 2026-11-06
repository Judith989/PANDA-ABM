"""Prepare a satellite alignment proposal ONLY; never writes data/lot_config.json."""
from pathlib import Path
import collections
import csv
import hashlib
import json
import math
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy.ndimage import gaussian_filter,map_coordinates

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'research/alignment_review/20261105'
R=6378137.


def main():
    before=OUT/'lot_config.before.json';raw=json.loads(before.read_text(encoding='utf8'))
    source_hash=hashlib.sha256(before.read_bytes()).hexdigest()
    assert hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest()==source_hash
    geo=json.loads((OUT/'imagery_georeference.json').read_text(encoding='utf8'));ext=geo['extent'];res=geo['resolution_mercator_m_per_pixel']
    photo=Image.open(OUT/'satellite.jpg').convert('RGB');gray=np.asarray(photo,dtype=float).mean(2)
    detail=np.clip(gray-gaussian_filter(gray,2),-10,20)
    def pixel(lon,lat):return ((R*math.radians(lon)-ext['xmin'])/res,(ext['ymax']-R*math.log(math.tan(math.pi/4+math.radians(lat)/2)))/res)
    def local(x,y):
        lon=math.degrees((ext['xmin']+x*res)/R);lat=math.degrees(2*math.atan(math.exp((ext['ymax']-y*res)/R))-math.pi/2)
        return ((lon-raw['meta']['ref_lon'])*111000*math.cos(math.radians(raw['meta']['ref_lat'])),(lat-raw['meta']['ref_lat'])*111000,lon,lat)
    groups=collections.defaultdict(list)
    for s in raw['slots']:groups[s['module']].append(s)
    fits=[];proposed=[];unresolved=[]
    for i,(module,records) in enumerate(groups.items()):
        if module.endswith(('_N','_Q')):
            unresolved.append(dict(module=module,source_records=len(records),reason='Merchandise/service area: individual ordinary car bays are not clearly supported by this image.'))
            continue
        pp=np.array([pixel(s['lon'],s['lat']) for s in records]);xc=float(np.median(pp[:,0]));y0=float(pp[:,1].min()+8);y1=float(pp[:,1].max()-8)
        angle=(30 if i%2==0 else -30)
        if module.endswith('_O'):xc=228.;y0=1080.;y1=1323.;angle=0
        if module.endswith('_P'):xc=1146.;y0=1069.;y1=1286.;angle=0
        ys=np.arange(math.ceil(y0),math.floor(y1))
        best=None
        for x in np.arange(xc-8,xc+8.1,2):
            for a in np.arange(angle-5,angle+5.1,1):
                xs=np.arange(x-8,x+8.1,1)
                coords=[ys[:,None]-math.tan(math.radians(a))*(xs[None,:]-x)+np.zeros((len(ys),len(xs))),np.broadcast_to(xs,(len(ys),len(xs)))]
                v=map_coordinates(detail,coords,order=1).mean(1);v-=v.mean()
                periods=np.arange(12.5,15.51,.05)
                waves=np.exp(-2j*np.pi*ys[:,None]/periods[None,:]);spectrum=v@waves/len(v);index=int(np.argmax(np.abs(spectrum)))
                score=float(abs(spectrum[index]));period=float(periods[index]);phase=float((-np.angle(spectrum[index])*period/(2*np.pi))%period)
                # Prefer a centre near the original reviewed row when evidence is tied.
                objective=score-.012*abs(x-xc)
                if best is None or objective>best[0]:best=(objective,x,float(a),period,phase,score)
        _,x,a,pitch,phase,score=best
        # Paint lines are boundaries; place each proposed centre midway between them.
        first=phase+pitch/2+math.ceil((y0-(phase+pitch/2))/pitch)*pitch
        centres=np.arange(first,y1+1e-6,pitch)
        fit=dict(module=module,pixel_x=round(x,3),pixel_y_min=round(y0,3),pixel_y_max=round(y1,3),heading_deg=a,pixel_pitch=round(pitch,3),paint_periodicity_score=round(score,3),proposed_bays=len(centres),original_records=len(records),review_status='row_fit_requires_visual_review')
        fits.append(fit)
        for k,y in enumerate(centres):
            east,north,lon,lat=local(x,float(y));ground_pixel=res*math.cos(math.radians(lat))
            width=pitch*ground_pixel*abs(math.cos(math.radians(a)));length=5.2 if abs(a)>10 else 5.0
            original=min(records,key=lambda s:math.dist((east,north),(s['local_x_m'],s['local_y_m'])))
            row=dict(id=f'REVIEW-{module.rsplit("_",1)[-1]}-{k+1:03d}',module=module,local_x_m=round(east,4),local_y_m=round(north,4),lon=lon,lat=lat,heading_deg=a,length_m=length,width_m=round(width,3),type='regular',is_accessible=False,is_reserved=False,is_unavailable=True,is_blocked=False,alignment_review_status='proposed_not_verified',restriction_review_status='not_assessed',nearest_original_id=original['id'])
            for group in ('walmart_doors','parking_lot_exits'):
                for point in raw[group]:row[f'distance_to_{point["id"]}_m']=round(math.dist((east,north),(point['local_x_m'],point['local_y_m'])),3)
            proposed.append(row)
    candidate={k:v for k,v in raw.items() if k!='slots'}
    candidate['meta']=dict(raw['meta'],lot_name=raw['meta']['lot_name']+' — alignment proposal',total_slots=len(proposed),modules=sorted({s['module'] for s in proposed}),accessible_slots=None,accessible_slot_ids=[],geometry_provenance=dict(alignment_status='unreviewed_row_fit',accuracy_class='estimated',horizontal_accuracy_m=None,imagery_capture_date=None,source=geo['service'],restrictions='Not assessed from imagery; all candidates disabled pending review.'),simulation_ready=False,alignment_status='pending_user_review',original_config_sha256=source_hash,imagery_source=geo['service'],imagery_copyright=geo['copyright'],note='Row-wise satellite fit. Original 1,315 records are not a verified painted-bay count. Proposed geometry uses new review IDs. Restriction labels are not established; all proposed bays remain unavailable to prevent accidental simulation use.')
    candidate['slots']=proposed
    (OUT/'lot_config.candidate.json').write_text(json.dumps(candidate,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    (OUT/'row_fits.json').write_text(json.dumps(dict(rows=fits,unresolved_areas=unresolved),indent=2)+'\n',encoding='utf8')
    def corners(s):
        a=math.radians(s.get('heading_deg',0));c=math.cos(a);sn=math.sin(a);l=s.get('length_m',4.9)/2;w=s.get('width_m',2.06)/2
        result=[]
        for dx,dy in [(-l,-w),(l,-w),(l,w),(-l,w)]:
            x=s['local_x_m']+dx*c-dy*sn;y=s['local_y_m']+dx*sn+dy*c
            result.append(pixel(raw['meta']['ref_lon']+x/(111000*math.cos(math.radians(raw['meta']['ref_lat']))),raw['meta']['ref_lat']+y/111000))
        return result
    im=photo.copy();d=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf',23);small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',18)
    for s in proposed:d.line(corners(s)+[corners(s)[0]],fill='#00f0ef',width=1)
    for fit in fits:
        text=fit['module'].rsplit('_',1)[-1];x=fit['pixel_x'];y=fit['pixel_y_min']-27
        d.text((x-8,y),text,fill='white',font=font,stroke_width=2,stroke_fill='black')
    for label,box in [('N: merchandise / curb area — review',(1250,500,1338,900)),('Q: service / loading area — review',(1100,1300,1210,1450))]:
        d.rectangle(box,outline='#ffae39',width=3);d.text((box[0]-130,box[1]-25),label,fill='#ffda89',font=small,stroke_width=2,stroke_fill='black')
    for key in ('walmart_doors','parking_lot_exits'):
        for p in raw[key]:
            x,y=pixel(p['lon'],p['lat']);d.ellipse((x-6,y-6,x+6,y+6),fill='#ffe000',outline='black',width=2);d.text((x+9,y-13),p['id'].replace('door_','Door ').replace('exit_','Access ').title(),fill='yellow',font=small,stroke_width=2,stroke_fill='black')
    footer=Image.new('RGB',(im.width,110),'#132b31');f=ImageDraw.Draw(footer)
    f.text((18,12),f'PROPOSAL ONLY: {len(proposed)} row-fitted bays; {len(raw["slots"])} original estimated records. Simulations unchanged.',fill='white',font=small)
    f.text((18,40),'Cyan: candidate bay geometry | Amber: unresolved area | Yellow: unchanged door/access markers',fill='white',font=small)
    f.text((18,68),geo['copyright']+' | Imagery date / survey accuracy not established.',fill='#d1e6e5',font=small)
    full=Image.new('RGB',(im.width,im.height+110));full.paste(im,(0,0));full.paste(footer,(0,im.height));full.save(OUT/'alignment_overlay.png')
    for name,box in [('main',(220,250,1340,970)),('west',(150,1010,310,1370)),('east',(1055,1000,1260,1470))]:
        im.crop(box).resize(((box[2]-box[0])*2,(box[3]-box[1])*2)).save(OUT/f'detail_{name}.png')
    old=[]
    for s in raw['slots']:old.append(dict(id=s['id'],corners=corners(s)))
    new=[dict(id=s['id'],corners=corners(s)) for s in proposed]
    payload=json.dumps(dict(width=photo.width,height=photo.height,original=old,candidate=new),separators=(',',':'))
    html='''<!doctype html><meta charset="utf-8"><title>Walmart alignment review</title><style>body{font:16px system-ui;background:#10242b;color:white;margin:20px}header{position:sticky;top:0;background:#10242bee;padding:12px;z-index:2}button,label{margin-right:15px}canvas{width:min(100%,1200px);height:auto;border:1px solid #63818c}a{color:cyan}</style><header><h2>Walmart parking geometry — review only</h2><p>Toggle the old estimates and candidate outlines. Cyan bays are row-fitted proposals, not individually surveyed spaces.</p><label><input id="old" type="checkbox">Original estimates</label><label><input id="new" type="checkbox" checked>Candidate angles and positions</label><label>Overlay opacity <input id="alpha" type="range" min="0" max="1" step=".05" value=".8"></label><p>All proposed restrictions remain unverified. Amber areas in the PNG need separate review. <a href="alignment_overlay.png">Annotated overview</a> · <a href="detail_west.png">West side</a> · <a href="detail_east.png">East side</a></p></header><canvas id="map"></canvas><p>Source: Esri World Imagery. Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community. Estimated alignment; imagery capture date unknown. No simulation files changed.</p><script>const data=PAYLOAD,canvas=document.querySelector('canvas'),ctx=canvas.getContext('2d'),im=new Image();canvas.width=data.width;canvas.height=data.height;function draw(){ctx.globalAlpha=1;ctx.drawImage(im,0,0);ctx.globalAlpha=Number(document.getElementById('alpha').value);for(const [key,color,id] of [['original','#ff69bb','old'],['candidate','#00f0ef','new']])if(document.getElementById(id).checked){ctx.strokeStyle=color;ctx.lineWidth=1;for(const s of data[key]){ctx.beginPath();s.corners.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.closePath();ctx.stroke();}}}for(const el of document.querySelectorAll('input'))el.oninput=draw;im.onload=draw;im.src='satellite.jpg';</script>'''.replace('PAYLOAD',payload)
    (OUT/'review.html').write_text(html,encoding='utf8')
    # Explicitly separate the preserved record inventory from the proposed painted-bay inventory.
    with (OUT/'row_inventory_comparison.csv').open('w',newline='',encoding='utf8') as h:
        writer=csv.DictWriter(h,fieldnames=list(fits[0]));writer.writeheader();writer.writerows(fits)
    assert hashlib.sha256((ROOT/'data/lot_config.json').read_bytes()).hexdigest()==source_hash
    print(json.dumps(dict(original_records=len(raw['slots']),proposed_bays=len(proposed),rows=len(fits),unresolved=unresolved,original_sha256=source_hash,simulation_config_unchanged=True)))

if __name__=='__main__':main()
