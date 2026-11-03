"""Render a layout-check SVG from draw.io geometry (not a diagrams.net export).

Only for inspecting placement; draw.io remains authoritative for rich text/math.
PNG asset bytes are embedded unchanged.
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import html,re,textwrap
ROOT=Path(__file__).resolve().parents[1];F=ROOT/'paper/figures'
tree=ET.parse(F/'framework_with_transparent_images.drawio')
root=tree.find('./diagram/mxGraphModel/root');cells={c.get('id'):c for c in root}
def style(c):
 return dict(t.split('=',1) for t in c.get('style','').split(';') if '=' in t)
def bounds(c):
 g=c.find('mxGeometry')
 if g is None:return (0,0,0,0)
 x,y,w,h=[float(g.get(k,'0')) for k in ('x','y','width','height')]
 p=c.get('parent')
 if p in cells and p not in ('0','1'):
  a,b,_,_=bounds(cells[p]);x+=a;y+=b
 return x,y,w,h
def esc(s):return html.escape(str(s),quote=True)
svg=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1800" height="1340" viewBox="0 0 1800 1340">','<rect width="1800" height="1340" fill="white"/>']
# Draw outer panels, then paths, then foreground boxes/text.
verts=[c for c in root if c.get('vertex')=='1']
def rect(c):
 s=style(c);x,y,w,h=bounds(c);fill=s.get('fillColor','#fff');stroke=s.get('strokeColor','#36566c')
 if fill=='none' and stroke=='none':return
 if 'image' in s:return
 if s.get('shape')=='rhombus':svg.append(f'<polygon points="{x+w/2},{y} {x+w},{y+h/2} {x+w/2},{y+h} {x},{y+h/2}" fill="{fill}" stroke="{stroke}"/>')
 else:svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{7 if s.get("rounded")=="1" else 0}" fill="{fill}" stroke="{stroke}"/>')
panels=[c for c in verts if bounds(c)[2]*bounds(c)[3]>70000 and not style(c).get('shape')=='image']
for c in panels:rect(c)
for c in root:
 if c.get('edge')!='1':continue
 s=style(c)
 if s.get('opacity')=='0':continue
 source=cells[c.get('source')];target=cells[c.get('target')]
 x,y,w,h=bounds(source);xx,yy,ww,hh=bounds(target)
 pts=[(x+w*float(s.get('exitX','.5')),y+h*float(s.get('exitY','.5')))]
 pts += [(float(p.get('x')),float(p.get('y'))) for p in c.findall('./mxGeometry/Array/mxPoint')]
 pts += [(xx+ww*float(s.get('entryX','.5')),yy+hh*float(s.get('entryY','.5')))]
 if len(pts)==2:
  a,b=pts
  if abs(a[0]-b[0])>5 and abs(a[1]-b[1])>5:pts=[a,(a[0],(a[1]+b[1])/2),(b[0],(a[1]+b[1])/2),b]
 color=s.get('strokeColor','#1767ab');dash=' stroke-dasharray="6 4"' if s.get('dashed')=='1' else ''
 svg.append(f'<polyline points="{" ".join(f"{a},{b}" for a,b in pts)}" fill="none" stroke="{color}" stroke-width="2"{dash}/>')
 a,b=pts[-2:];dx,dy=b[0]-a[0],b[1]-a[1];norm=max((dx*dx+dy*dy)**.5,.001);ux,uy=dx/norm,dy/norm
 svg.append(f'<polygon points="{b[0]},{b[1]} {b[0]-ux*9-uy*4},{b[1]-uy*9+ux*4} {b[0]-ux*9+uy*4},{b[1]-uy*9-ux*4}" fill="{color}"/>')
 label=html.unescape(re.sub('<[^>]+>',' ',c.get('value','').replace('<br>',' ')))
 if label:
  mid=pts[len(pts)//2];lines=textwrap.wrap(label,30);width=min(210,max(len(t) for t in lines)*6.5+8);height=len(lines)*15+4
  svg.append(f'<rect x="{mid[0]-width/2}" y="{mid[1]-height/2}" width="{width}" height="{height}" fill="white"/>')
  for j,line in enumerate(lines):svg.append(f'<text x="{mid[0]}" y="{mid[1]-height/2+13+j*15}" text-anchor="middle" font-family="Arial" font-size="12" fill="{color}">{esc(line)}</text>')
for c in verts:
 s=style(c);x,y,w,h=bounds(c)
 if c not in panels:rect(c)
 if 'image' in s:
  uri=s['image'].replace('data:image/png,','data:image/png;base64,')
  svg.append(f'<image x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid meet" href="{uri}"/>')
  continue
 value=c.get('value','')
 if not value:continue
 value=re.sub(r'<br\s*/?>','\n',value,flags=re.I);value=html.unescape(re.sub('<[^>]+>','',value))
 font=float(s.get('fontSize','15'));align=s.get('align','center');left=align=='left'
 def lines_at(size):
  limit=max(8,int((w-12)/(size*.53)));return [line for part in value.split('\n') for line in (textwrap.wrap(part,limit) or [''])]
 lines=lines_at(font)
 while len(lines)*font*1.2>h-4 and font>9:font-=.5;lines=lines_at(font)
 total=len(lines)*font*1.2;start=y+(h-total)/2+font
 for j,line in enumerate(lines):svg.append(f'<text x="{x+6 if left else x+w/2}" y="{start+j*font*1.2}" text-anchor="{"start" if left else "middle"}" font-family="Arial" font-size="{font}" font-weight="{"bold" if s.get("fontStyle")=="1" else "normal"}" fill="#173449">{esc(line)}</text>')
svg.append('</svg>');(F/'framework_illustrated_layout_preview.svg').write_text('\n'.join(svg),encoding='utf-8')
print('Created SVG layout preview; rich text simplified only in preview.')
