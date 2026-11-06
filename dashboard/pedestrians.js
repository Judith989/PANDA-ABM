/* Pedestrian display follows the ABM's walking timestamps, independent of car paths. */
(function(root){
  function position(intervals,t){
    const leg=(intervals??[]).find(p=>p.end_s>p.start_s&&t>=p.start_s&&(t<p.end_s||(p.source==='simulated_network_walk'&&t===p.end_s&&p===(intervals??[]).at(-1))));if(!leg)return null;
    const f=(t-leg.start_s)/(leg.end_s-leg.start_s),dx=leg.to_m[0]-leg.from_m[0],dy=leg.to_m[1]-leg.from_m[1],d=Math.hypot(dx,dy);
    return {x:leg.from_m[0]+f*dx,y:leg.from_m[1]+f*dy,direction:d?[dx/d,dy/d]:[0,0],phase:leg.phase,elapsed_s:t-leg.start_s,leg};
  }
  function legacyIntervals(track,slots,doors,speed=1.4){
    const result=[],samples=track.samples;
    for(let i=0;i<samples.length;i++){
      const row=samples[i],state=row[3];if(!['walking_to_destination','returning_to_vehicle'].includes(state))continue;
      if(i&&samples[i-1][3]===state)continue;
      const bay=slots.find(s=>s.id===row[4]),door=doors.find(d=>d.id===track.door);if(!bay||!door)continue;
      const from=[bay.local_x_m,bay.local_y_m],to=[door.local_x_m,door.local_y_m];let j=i+1;while(j<samples.length&&samples[j][3]===state)j++;
      const end=j<samples.length?samples[j][0]:row[0]+Math.hypot(from[0]-to[0],from[1]-to[1])/speed;
      const returning=state==='returning_to_vehicle';
      result.push({phase:returning?'to_vehicle':'to_door',start_s:row[0],end_s:end,from_m:returning?to:from,to_m:returning?from:to,door:track.door,space:row[4],source:'legacy_recorded_state_transitions'});
    }
    return result;
  }
  root.PandaPedestrians={position,legacyIntervals};
})(typeof window==='undefined'?globalThis:window);
