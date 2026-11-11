/* Route-aware display interpolation. No simulation decisions or clock changes. */
(function(root){
  const cache=new WeakMap();
  const distance=(a,b)=>Math.hypot(a[0]-b[0],a[1]-b[1]);
  function onSegment(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy;if(l<1e-12)return distance(p,a)<1e-5;const t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l;return t>=-1e-6&&t<=1+1e-6&&distance(p,[a[0]+t*dx,a[1]+t*dy])<1e-4;}
  function interpolate(a,b,t,edges=[]){
    const result={x:a[1],y:a[2],direction:[0,0]};if(!b||b[0]<=a[0]||b[0]-a[0]>1.001)return result;
    const driving=['searching','targeting','exiting'];
    if(a[3]!==b[3]&&!driving.includes(a[3]))return result;
    let path=cache.get(a);
    if(!path||path.next!==b){
      let points=b[6]?.length?b[6]:null;
      if(points&&(distance(points[0],[a[1],a[2]])>1e-4||distance(points.at(-1),[b[1],b[2]])>1e-4))points=null;
      // Older archives have no corner vertices: interpolate only on one known edge.
      if(!points&&edges.some(([p,q])=>onSegment([a[1],a[2]],p,q)&&onSegment([b[1],b[2]],p,q)))points=[[a[1],a[2]],[b[1],b[2]]];
      const lengths=points?points.slice(1).map((p,i)=>distance(points[i],p)):[];
      path={next:b,points,lengths,total:lengths.reduce((v,n)=>v+n,0)};cache.set(a,path);
    }
    if(!path.points||path.total<1e-9)return result;
    let remaining=Math.max(0,Math.min(1,(t-a[0])/(b[0]-a[0])))*path.total;
    for(let i=0;i<path.lengths.length;i++){
      const l=path.lengths[i];if(l<1e-9)continue;
      if(remaining<=l||i===path.lengths.length-1){const p=path.points[i],q=path.points[i+1],f=Math.min(1,remaining/l);return {x:p[0]+(q[0]-p[0])*f,y:p[1]+(q[1]-p[1])*f,direction:[(q[0]-p[0])/l,(q[1]-p[1])/l]};}
      remaining-=l;
    }
    return result;
  }
  // Matches LANE_SNAP_M in panda_abm/core/bay_clearance.py: a vehicle within 0.5 m of an aligned road is in its lane.
  function nearSegment(p,a,b,tolerance=.5){const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy;if(l<1e-12)return distance(p,a)<tolerance;const t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l));return distance(p,[a[0]+t*dx,a[1]+t*dy])<tolerance;}
  function laneOffset(point,direction,edges){
    const norm=Math.hypot(...direction);if(norm<1e-8)return [0,0];const u=direction.map(v=>v/norm);
    // Like the model, only road edges (not bay approach spurs) carry lanes.
    const edge=edges.find(e=>!e.spur&&nearSegment(point,e.a,e.b)&&Math.abs((e.b[0]-e.a[0])*u[0]+(e.b[1]-e.a[1])*u[1])/distance(e.a,e.b)>.99);
    return edge?[u[1]*1.2,-u[0]*1.2]:[0,0];
  }
  // Display-only separation of moving vehicles. The simulation can briefly let a
  // held vehicle pass through another (deadlock release) or leave a vehicle waiting
  // half in the lane beside a bay; drawing those bodies on top of each other looks
  // like a collision. Positions here are cosmetic: model state is never changed.
  const DIMENSIONS={compact:[3.9,1.72],sedan:[4.55,1.82],suv:[4.75,1.94],van:[5.15,2.0],truck:[5.45,2.02]};
  // GAP adds bumper clearance along the vehicle so separated cars read as a queue.
  const GAP=.4;
  function footprint(v,back=0,pad=0){
    const [length,w]=DIMENSIONS[v.type]??DIMENSIONS.sedan,l=length+pad,u=v.direction,n=[-u[1],u[0]],x=v.x-u[0]*back,y=v.y-u[1]*back;
    return [[1,1],[1,-1],[-1,-1],[-1,1]].map(([i,j])=>[x+u[0]*i*l/2+n[0]*j*w/2,y+u[1]*i*l/2+n[1]*j*w/2]);
  }
  function overlaps(a,b){
    for(const poly of [a,b])for(let i=0;i<4;i++){
      const p=poly[i],q=poly[(i+1)%4],axis=[q[1]-p[1],p[0]-q[0]];
      const pa=a.map(c=>c[0]*axis[0]+c[1]*axis[1]),pb=b.map(c=>c[0]*axis[0]+c[1]*axis[1]);
      if(Math.max(...pa)<=Math.min(...pb)+1e-6||Math.max(...pb)<=Math.min(...pa)+1e-6)return false;
    }
    return true;
  }
  // vehicles: [{id,x,y,direction:[ux,uy] (unit),type}] -> Map id -> [x,y] for vehicles that must move.
  function separate(vehicles,maxShift=20,step=.25){
    const items=vehicles.filter(v=>Math.hypot(...v.direction)>1e-8).map(v=>({...v,back:0})).sort((a,b)=>String(a.id).localeCompare(String(b.id)));
    // A stacked queue resolves one vehicle per pass, so repeat until nothing moves.
    for(let pass=0;pass<12;pass++){
      let moved=false;
      for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){
        const a=items[i],b=items[j];
        if(Math.hypot(a.x-a.direction[0]*a.back-b.x+b.direction[0]*b.back,a.y-a.direction[1]*a.back-b.y+b.direction[1]*b.back)>7)continue;
        if(!overlaps(footprint(a,a.back),footprint(b,b.back)))continue;  // only real body overlaps trigger a shift
        // The vehicle behind the other along its own heading gives way; ties fall to the later id.
        const behind=(v,o)=>((o.x-v.x)*v.direction[0]+(o.y-v.y)*v.direction[1])>0;
        const follower=behind(b,a)&&!behind(a,b)?b:behind(a,b)&&!behind(b,a)?a:b,other=follower===a?b:a;
        while(follower.back<maxShift&&overlaps(footprint(follower,follower.back,GAP),footprint(other,other.back,GAP)))follower.back+=step;
        moved=true;
      }
      if(!moved)break;
    }
    return new Map(items.filter(v=>v.back>0).map(v=>[v.id,[v.x-v.direction[0]*v.back,v.y-v.direction[1]*v.back]]));
  }
  root.PandaMotion={interpolate,laneOffset,onSegment,separate};
})(typeof window==='undefined'?globalThis:window);
