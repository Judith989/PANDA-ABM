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
  function laneOffset(point,direction,edges){
    const norm=Math.hypot(...direction);if(norm<1e-8)return [0,0];const u=direction.map(v=>v/norm);
    const edge=edges.find(e=>onSegment(point,e.a,e.b)&&Math.abs((e.b[0]-e.a[0])*u[0]+(e.b[1]-e.a[1])*u[1])/distance(e.a,e.b)>.99);
    return edge&&!edge.spur?[u[1]*1.2,-u[0]*1.2]:[0,0];
  }
  root.PandaMotion={interpolate,laneOffset,onSegment};
})(typeof window==='undefined'?globalThis:window);
