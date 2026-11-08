/* Pedestrian display follows the ABM's walking timestamps, independent of car paths. */
(function(root){
  function position(intervals,t,stillWalking=false){
    let leg=(intervals??[]).find(p=>p.end_s>p.start_s&&t>=p.start_s&&(t<p.end_s||(p.source==='simulated_network_walk'&&t===p.end_s&&p===(intervals??[]).at(-1))));
    if(!leg&&stillWalking){
      // Live frames record a walk up to the previous engine second. While the
      // driver is still walking, hold them at the latest recorded point.
      const last=(intervals??[]).filter(p=>p.start_s<=t).at(-1);
      if(last){const dx=last.to_m[0]-last.from_m[0],dy=last.to_m[1]-last.from_m[1],d=Math.hypot(dx,dy);
        return {x:last.to_m[0],y:last.to_m[1],direction:d?[dx/d,dy/d]:[0,0],phase:last.phase,elapsed_s:t-last.start_s,leg:{...last,waiting:true}};}
    }
    if(!leg)return null;
    const f=(t-leg.start_s)/(leg.end_s-leg.start_s),dx=leg.to_m[0]-leg.from_m[0],dy=leg.to_m[1]-leg.from_m[1],d=Math.hypot(dx,dy);
    return {x:leg.from_m[0]+f*dx,y:leg.from_m[1]+f*dy,direction:d?[dx/d,dy/d]:[0,0],phase:leg.phase,elapsed_s:t-leg.start_s,leg};
  }
  // Shortest walking-network path from a bay to a destination (display only).
  const routes=new WeakMap();
  function networkRoute(network,spaceId,doorId){
    const source=network?.space_access?.[spaceId],target=network?.destination_access?.[doorId];if(!source||!target)return null;
    let cache=routes.get(network);
    if(!cache){
      const adjacency=new Map();
      for(const e of network.edges){const w=Math.hypot(network.nodes[e.from][0]-network.nodes[e.to][0],network.nodes[e.from][1]-network.nodes[e.to][1]);
        for(const [a,b] of [[e.from,e.to],[e.to,e.from]]){if(!adjacency.has(a))adjacency.set(a,[]);adjacency.get(a).push([b,w]);}}
      cache={adjacency,paths:new Map()};routes.set(network,cache);
    }
    const key=spaceId+'|'+doorId;if(cache.paths.has(key))return cache.paths.get(key);
    const start=source.node,goal=target.node??target,dist=new Map([[start,0]]),previous=new Map(),heap=[[0,start]];
    const push=item=>{heap.push(item);let i=heap.length-1;while(i){const p=(i-1)>>1;if(heap[p][0]<=heap[i][0])break;[heap[p],heap[i]]=[heap[i],heap[p]];i=p;}};
    const pop=()=>{const top=heap[0],last=heap.pop();if(heap.length){heap[0]=last;let i=0;for(;;){const l=2*i+1,r=l+1;let m=i;if(l<heap.length&&heap[l][0]<heap[m][0])m=l;if(r<heap.length&&heap[r][0]<heap[m][0])m=r;if(m===i)break;[heap[m],heap[i]]=[heap[i],heap[m]];i=m;}}return top;};
    while(heap.length){const [d,n]=pop();if(d>dist.get(n))continue;if(n===goal)break;for(const [m,w] of cache.adjacency.get(n)??[]){if(d+w<(dist.get(m)??Infinity)){dist.set(m,d+w);previous.set(m,n);push([d+w,m]);}}}
    let path=null;
    if(dist.has(goal)){const nodes=[goal];while(nodes[0]!==start)nodes.unshift(previous.get(nodes[0]));path=[...source.points.map(p=>[p[0],p[1]]),...nodes.slice(1).map(n=>network.nodes[n])];}
    cache.paths.set(key,path);return path;
  }
  function legacyIntervals(track,slots,doors,speed=1.4,network=null){
    const result=[],samples=track.samples;
    for(let i=0;i<samples.length;i++){
      const row=samples[i],state=row[3];if(!['walking_to_destination','returning_to_vehicle'].includes(state))continue;
      if(i&&samples[i-1][3]===state)continue;
      const bay=slots.find(s=>s.id===row[4]),door=doors.find(d=>d.id===track.door);if(!bay||!door)continue;
      const from=[bay.local_x_m,bay.local_y_m],to=[door.local_x_m,door.local_y_m];let j=i+1;while(j<samples.length&&samples[j][3]===state)j++;
      const end=j<samples.length?samples[j][0]:row[0]+Math.hypot(from[0]-to[0],from[1]-to[1])/speed;
      const returning=state==='returning_to_vehicle';
      // Older recordings stored only state changes. Draw the walk along the
      // configured walking network (never across parked bays) when one exists.
      let points=network?networkRoute(network,bay.id,track.door):null;
      if(!points||points.length<2)points=[from,to];
      if(returning)points=[...points].reverse();
      const lengths=points.slice(1).map((p,k)=>Math.hypot(p[0]-points[k][0],p[1]-points[k][1])),total=lengths.reduce((a,b)=>a+b,0)||1;
      let clock=row[0];
      for(let k=0;k<lengths.length;k++){
        const duration=(end-row[0])*lengths[k]/total;
        result.push({phase:returning?'to_vehicle':'to_door',start_s:clock,end_s:clock+duration,from_m:points[k],to_m:points[k+1],door:track.door,space:row[4],source:points.length>2?'legacy_states_network_path':'legacy_recorded_state_transitions'});
        clock+=duration;
      }
    }
    return result;
  }
  root.PandaPedestrians={position,legacyIntervals,networkRoute};
})(typeof window==='undefined'?globalThis:window);
