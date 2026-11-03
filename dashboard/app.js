/* Display adapter only: all decisions, claims and movement come from Python. */
const $ = id => document.getElementById(id);
const C = window.Cesium;
const state = {scene:null, run:null, id:null, time:0, playing:false, selected:null, live:null, slotEntities:new Map(), drivers:new Map(), parkedCars:new Map(), context:[], networks:[]};
const infoText = {unaided:'Drivers find spaces by observing nearby bays as they drive.',aisle:'Drivers know how many usable free spaces are in each aisle, then search within it.',space:'Drivers know which individual spaces are free and can head toward one. Spaces are not reserved.'};
const colors = {free:'#65ac82',occupied:'#ce7950',blocked:'#89928b'};
let viewer, lastTick, appliedTime=-1;
const modelNames = {cpt:'CPT',rum:'M1',deterministic:'M0'};
const esc = value => String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = seconds => `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
async function api(url, options) {return window.PandaPlatform.api(url,options);}
function local(x,y,height=.25) {
  const meta=state.scene.config.meta;
  // Inverse of the exact small-site conversion used by the current ABM.
  return C.Cartesian3.fromDegrees(meta.ref_lon+x/(111000*Math.cos(meta.ref_lat*Math.PI/180)),meta.ref_lat+y/111000,height);
}
function lastAt(samples,t) {
  let low=0,high=samples.length-1;
  while(low<high){const mid=Math.ceil((low+high)/2);if(samples[mid][0]<=t)low=mid;else high=mid-1;}
  return low;
}
function sample(track,t) {
  const i=lastAt(track.samples,t),a=track.samples[i],b=track.samples[i+1];
  let x=a[1],y=a[2];
  if(b&&a[3]===b[3]&&b[0]-a[0]<=1.001){const f=Math.max(0,Math.min(1,(t-a[0])/(b[0]-a[0])));x+=(b[1]-x)*f;y+=(b[2]-y)*f;}
  return {x,y,state:a[3],space:a[4],search:a[5]};
}
function home(overhead=false) {
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(local(25,-27,0),185),{
    offset:new C.HeadingPitchRange(0,overhead?-Math.PI/2:-Math.PI/3,overhead?440:490),duration:1});
}
function slotColor(slot,occupied) {return C.Color.fromCssColorString(slot.is_blocked||slot.is_unavailable?colors.blocked:occupied?colors.occupied:colors.free).withAlpha(.85);}
function createScene() {
  viewer = new C.Viewer('cesiumContainer',{baseLayer:false,baseLayerPicker:false,terrainProvider:new C.EllipsoidTerrainProvider(),
    animation:false,timeline:false,geocoder:false,homeButton:false,sceneModePicker:true,navigationHelpButton:true,
    fullscreenButton:true,selectionIndicator:true,infoBox:false,shouldAnimate:false});
  viewer.imageryLayers.addImageryProvider(new C.OpenStreetMapImageryProvider({url:'https://tile.openstreetmap.org/'}));
  viewer.scene.globe.baseColor=C.Color.fromCssColorString('#e3e8dc');
  viewer.scene.backgroundColor=C.Color.fromCssColorString('#edf1e9');
  viewer.scene.skyBox.show=false;viewer.scene.skyAtmosphere.show=false;viewer.scene.sun.show=false;viewer.scene.moon.show=false;
  viewer.scene.globe.enableLighting=false;
  for(const slot of state.scene.config.slots) {
    const x=slot.local_x_m,y=slot.local_y_m;
    const e=viewer.entities.add({id:'slot:'+slot.id,name:slot.id,
      polygon:{hierarchy:new C.PolygonHierarchy([local(x-2.45,y-1.03),local(x+2.45,y-1.03),local(x+2.45,y+1.03),local(x-2.45,y+1.03)]),
        perPositionHeight:true,material:slotColor(slot,false),outline:false}});
    state.slotEntities.set(slot.id,{entity:e,slot,occupied:false});
  }
  const config=state.scene.config;
  const landmarks=[...(config.walmart_doors||[]).map((p,i)=>({...p,name:`Door ${i+1}`,color:'#163a34'})),
    ...(config.parking_lot_exits||config.entry_points||[]).map((p,i)=>({...p,name:`Entry / Exit ${i===0?'A':'B'}`,color:'#986326'}))];
  for(const p of landmarks) {
    const pos=p.local_x_m!==undefined?local(p.local_x_m,p.local_y_m,2):C.Cartesian3.fromDegrees(p.lon,p.lat,2);
    viewer.entities.add({id:'landmark:'+p.id,name:p.name,position:pos,
      point:{pixelSize:11,color:C.Color.fromCssColorString(p.color),outlineColor:C.Color.WHITE,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
      label:{text:p.name,font:'bold 13px sans-serif',fillColor:C.Color.WHITE,showBackground:true,backgroundColor:C.Color.fromCssColorString(p.color),
        pixelOffset:new C.Cartesian2(0,-22),disableDepthTestDistance:Number.POSITIVE_INFINITY}});
  }
  viewer.screenSpaceEventHandler.setInputAction(click=>{
    const hit=viewer.scene.pick(click.position);
    if(hit&&hit.id){state.selected=hit.id.id;inspect();}
  },C.ScreenSpaceEventType.LEFT_CLICK);
  home();
}
async function loadContext() {
  const a=state.scene.alignment;
  if(!a){$('show-context').checked=false;$('show-context').disabled=true;$('alignment-note').textContent='3D assets have not been prepared. The corrected simulation geometry is displayed.';return;}
  $('alignment-note').textContent=`${a.matched_ids.toLocaleString()} matched space IDs. Scene-fit RMS residual: ${a.fit_rmse_m.toFixed(2)} m. Slot markers are positioned directly from the corrected JSON.`;
  const enu=C.Transforms.eastNorthUpToFixedFrame(local(a.east_m,a.north_m,a.height_m));
  const rotation=C.Matrix4.fromRotationTranslation(C.Matrix3.fromRotationZ(a.rotation_radians));
  const transform=C.Matrix4.multiply(enu,rotation,new C.Matrix4());C.Matrix4.multiplyByUniformScale(transform,a.scale,transform);
  const results=await Promise.allSettled(['parking_asphalt.glb','walmart_building.glb'].map(async name=>{
    // Our fit assumes glTF (x,y,z) -> ENU (x,-z,y). Disabling the
    // default Z-forward adaptation prevents an extra rotation of the scene.
    const model=await C.Model.fromGltfAsync({url:'assets/'+name,modelMatrix:transform,
      upAxis:C.Axis.Y,forwardAxis:C.Axis.X,allowPicking:false});
    viewer.scene.primitives.add(model);state.context.push(model);return model;
  }));
  const failed=results.filter(r=>r.status==='rejected');
  if(failed.length){$('map-status').textContent='Some 3D context assets could not load. Corrected spaces and replay remain available.';console.error(failed);}
  else $('map-status').hidden=true;
}
function showNetwork(edges) {
  for(const e of state.networks)viewer.entities.remove(e);state.networks=[];
  for(const [a,b] of edges)state.networks.push(viewer.entities.add({polyline:{positions:[local(a[0],a[1],.14),local(b[0],b[1],.14)],width:1,
    material:C.Color.fromCssColorString('#a6bda1').withAlpha(.6)},show:$('show-network').checked}));
}
async function refreshHistory(selected) {
  const runs=await api('/api/runs');
  $('history').replaceChildren(...runs.filter(r=>r.status==='complete').map(r=>{
    const o=document.createElement('option');o.value=r.id;
    o.textContent=`${r.id==='baseline'?'Reference':'Run '+r.id.slice(0,5)} · ${modelNames[r.settings.model]} / ${r.settings.information} / ${Math.round(100*r.settings.occupancy)}%`;
    return o;
  }));
  if(selected)$('history').value=selected;
}
async function loadRun(id) {
  await closeLive();
  $('job-status').textContent='Loading replay…';setPlaying(false);
  const data=await api(`/api/runs/${id}/data`);state.run=data;state.id=id;state.time=0;state.selected=null;appliedTime=-1;
  for(const e of state.drivers.values())viewer.entities.remove(e);state.drivers.clear();
  for(const e of state.parkedCars.values())viewer.entities.remove(e);state.parkedCars.clear();
  for(const track of data.tracks) {
    const e=viewer.entities.add({id:'driver:'+track.id,name:track.id,position:local(0,0,1),
      box:{dimensions:new C.Cartesian3(4.3,1.9,1.5),material:C.Color.fromCssColorString('#176ba4'),outline:true,outlineColor:C.Color.WHITE},
      point:{pixelSize:9,color:C.Color.fromCssColorString('#176ba4'),outlineColor:C.Color.WHITE,outlineWidth:1.5,disableDepthTestDistance:Number.POSITIVE_INFINITY}});
    state.drivers.set(track.id,e);
    state.parkedCars.set(track.id,viewer.entities.add({id:'parked:'+track.id,name:track.id,show:false,position:local(0,0,1),box:{dimensions:new C.Cartesian3(4.3,1.9,1.5),material:C.Color.fromCssColorString('#176ba4')}}));
  }
  showNetwork(data.aisle_edges);
  $('timeline').max=data.duration_s;$('timeline').value=0;$('duration').textContent=formatTime(data.duration_s);
  $('run-title').textContent=id==='baseline'?'Saved reference run':'Your simulation';
  $('view-mode').textContent='SAVED REPLAY · CESIUMJS 3D';
  const s=data.settings;$('run-description').textContent=`${modelNames[s.model]} / ${s.information} information / ${Math.round(100*s.occupancy)}% initial occupancy / ${s.population_size} drivers / seed ${s.seed}`;
  const n=v=>v===null?'—':v.toFixed(1);
  $('outcomes').innerHTML=`Parked <b>${data.summary.parked} / ${data.summary.drivers}</b><br>Mean search <b>${n(data.summary.mean_search_s)} s</b><br>Mean walk <b>${n(data.summary.mean_walk_m)} m</b><br>Mean intended-exit distance <b>${n(data.summary.mean_exit_m)} m</b>`;
  $('verification').textContent=data.verification?`✓ ${data.verification.status}. Physical replay samples: 1 second.`:'Current Python ABM run · configuration, population and source hashes included in the download · physical samples: 1 second.';
  $('job-status').textContent='Replay ready. Press play or drag the timeline.';
  chart();render();await refreshHistory(id);
}
function chart() {
  const run=state.run,cap=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
  const points=run.system.map(row=>`${45+row[0]/run.duration_s*600},${120-row[1]/cap*95}`).join(' ');
  $('chart').innerHTML=`<line x1="45" y1="120" x2="645" y2="120" stroke="#dce6da"/><line x1="45" y1="25" x2="645" y2="25" stroke="#edf1e9"/><text x="1" y="28" fill="#748575" font-size="13">100%</text><text x="15" y="123" fill="#748575" font-size="13">0%</text><polyline points="${points}" fill="none" stroke="#398565" stroke-width="3"/><line id="chart-cursor" x1="45" x2="45" y1="20" y2="125" stroke="#a8b938" stroke-width="2"/><text x="45" y="146" fill="#748575" font-size="12">00:00</text><text x="590" y="146" fill="#748575" font-size="12">${formatTime(run.duration_s)}</text>`;
}
function render() {
  if(!state.run)return;
  const t=state.time,run=state.run;
  for(const track of run.tracks) {
    const p=sample(track,t),e=state.drivers.get(track.id);
    e.show=!['not_arrived','left','abandoned','at_destination'].includes(p.state);
    const walking=['walking_to_destination','returning_to_vehicle'].includes(p.state);
    if(e.show){
      e.position=local(p.x,p.y,1);e.point.show=walking;e.box.show=!walking;
      e.point.color=C.Color.fromCssColorString(walking?'#a77b27':'#176ba4');
      const next=sample(track,Math.min(run.duration_s,t+.5));
      if(Math.hypot(next.x-p.x,next.y-p.y)>.01)e.orientation=C.Transforms.headingPitchRollQuaternion(local(p.x,p.y,1),new C.HeadingPitchRoll(-Math.atan2(next.y-p.y,next.x-p.x),0,0));
    }
    const parked=state.parkedCars.get(track.id),slot=state.slotEntities.get(p.space);
    if(parked){parked.show=Boolean(slot&&(walking||p.state==='at_destination'));if(parked.show)parked.position=local(slot.slot.local_x_m,slot.slot.local_y_m,1);}
  }
  if(Math.floor(t)!==appliedTime) {
    appliedTime=Math.floor(t);
    const occupied=new Set(run.initial_occupied);
    for(const [time,added,removed] of run.occupancy_changes){if(time>t)break;for(const id of added)occupied.add(id);for(const id of removed)occupied.delete(id);}
    for(const [id,item] of state.slotEntities){const taken=occupied.has(id);if(item.occupied!==taken||t<1){item.occupied=taken;item.entity.polygon.material=slotColor(item.slot,taken);}}
    const row=run.system[lastAt(run.system,t)];
    $('parked').textContent=row[3];$('searching').textContent=row[2];$('abandoned').textContent=row[4];
    const cap=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
    $('occupied').textContent=(occupied.size/cap*100).toFixed(1)+'%';inspect();
  }
  $('timeline').value=t;$('time').textContent=formatTime(t);
  const cursor=$('chart-cursor');if(cursor){const x=45+t/run.duration_s*600;cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);}
}
function inspect() {
  if(!state.selected||!state.run){$('inspection').textContent='Click a driver or a parking space on the map to inspect it.';return;}
  const [kind,id]=state.selected.split(':');
  if(kind==='driver'||kind==='parked'){
    const track=state.run.tracks.find(x=>x.id===id);if(!track)return;
    const p=sample(track,state.time);
    $('inspection').innerHTML=`<b>${esc(id)}</b> · ${esc(p.state.replaceAll('_',' '))}<br>Destination: ${esc(track.door?.replace('door_','Door '))}<br>Intended exit: ${esc(track.intended_exit?.replace('exit_a','A').replace('exit_b','B'))}<br>Chosen space: ${esc(p.space)}<br>Elapsed search: ${p.search.toFixed(1)} s`;
  }else if(kind==='slot'){
    const item=state.slotEntities.get(id),s=item.slot;
    $('inspection').innerHTML=`<b>${esc(id)}</b> · ${s.is_unavailable?'Blocked':item.occupied?'Occupied':'Free'}<br>Door 1 / 2: ${s.distance_to_door_1_m.toFixed(1)} / ${s.distance_to_door_2_m.toFixed(1)} m<br>Exit A / B: ${s.distance_to_exit_a_m.toFixed(1)} / ${s.distance_to_exit_b_m.toFixed(1)} m<br><span class="help">Straight-line distances</span>`;
  }else $('inspection').textContent=id;
}
function setPlaying(playing){state.playing=playing;$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'Pause replay':'Play replay');lastTick=undefined;}
function tick(now){if(lastTick&&state.playing&&state.run){state.time=Math.min(state.run.duration_s,state.time+(now-lastTick)/1000*Number($('speed').value));render();if(state.time===state.run.duration_s&&(!state.live||state.live.complete))setPlaying(false);}if(state.live&&state.playing&&!state.live.complete&&!state.live.busy&&state.run.duration_s-state.time<Number($('speed').value)*1.5)pumpLive();lastTick=now;requestAnimationFrame(tick);}
function settingsFromForm(){return {model:$('model').value,information:$('information').value,occupancy:Number($('occupancy').value)/100,
  population_size:Number($('population').value),arrival_interval_s:Number($('arrivals').value),seed:Number($('seed').value)};}
async function closeLive(){if(!state.live)return;const id=state.live.id;state.live=null;await api('/api/live/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'close'})}).catch(()=>{});}
function appendFrames(frames){
  const run=state.run;
  for(const frame of frames){
    for(let i=0;i<frame.vehicles.length;i++){
      const row=frame.vehicles[i],track=run.tracks[i];
      track.samples.push([frame.time_s,...row.slice(1)]);
    }
    if(frame.added.length||frame.removed.length)run.occupancy_changes.push([frame.time_s,frame.added,frame.removed]);
    run.system.push(frame.system);run.duration_s=Math.max(1,frame.time_s);
  }
  $('timeline').max=run.duration_s;$('duration').textContent=formatTime(run.duration_s);chart();
}
async function startLive(){
  if(!$('scenario').reportValidity())return;
  $('live-button').disabled=true;
  try{
    setPlaying(false);await closeLive();
    $('job-status').textContent='Starting a live Python simulation…';
    const live=await api('/api/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settingsFromForm())});
    state.live={id:live.id,busy:false,complete:false};state.id=live.id;state.time=0;state.selected=null;appliedTime=-1;
    state.run={schema_version:1,settings:live.settings,population:live.population,source_sha256:live.source_sha256,initial_occupied:live.initial_occupied,
      tracks:live.tracks,occupancy_changes:[],system:[],aisle_edges:live.aisle_edges,duration_s:1,live:true};
    for(const e of state.drivers.values())viewer.entities.remove(e);state.drivers.clear();
    for(const e of state.parkedCars.values())viewer.entities.remove(e);state.parkedCars.clear();
    for(const track of live.tracks){state.drivers.set(track.id,viewer.entities.add({id:'driver:'+track.id,name:track.id,position:local(0,0,1),
      box:{dimensions:new C.Cartesian3(4.3,1.9,1.5),material:C.Color.fromCssColorString('#176ba4'),outline:true,outlineColor:C.Color.WHITE},
      point:{pixelSize:10,color:C.Color.fromCssColorString('#176ba4'),outlineColor:C.Color.WHITE,outlineWidth:2,disableDepthTestDistance:Infinity}}));
      state.parkedCars.set(track.id,viewer.entities.add({id:'parked:'+track.id,name:track.id,show:false,position:local(0,0,1),box:{dimensions:new C.Cartesian3(4.3,1.9,1.5),material:C.Color.fromCssColorString('#176ba4')}}));}
    appendFrames([live.frame]);showNetwork(live.aisle_edges);
    $('view-mode').textContent='LIVE SIMULATION · CESIUMJS 3D';$('run-title').textContent='Live parking simulation';
    const s=live.settings;$('run-description').textContent=`${modelNames[s.model]} / ${s.information} / ${s.population_size} drivers / ${Math.round(s.occupancy*100)}% occupancy / seed ${s.seed}`;
    $('outcomes').textContent='Simulation in progress. Final outcomes will appear when every driver has left or abandoned.';
    $('verification').textContent='Live updates from the current Python ABM. Pause stops requests for further steps. Scenario changes take effect when you start a new run.';
    render();setPlaying(true);await pumpLive();
  }catch(error){$('job-status').textContent=error.message;}finally{$('live-button').disabled=false;}
}
async function pumpLive(){
  const live=state.live;if(!live||live.busy)return;live.busy=true;
  try{
    const data=await api('/api/live/'+live.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds:Math.min(120,Math.max(1,Math.ceil(Number($('speed').value))))})});
    if(state.live!==live)return;appendFrames(data.frames);live.complete=data.complete;state.run.summary=data.summary;
    $('job-status').textContent=data.complete?'Live simulation complete. You can replay or download this run.':'Live Python model · '+formatTime(data.time_s)+' simulated · pause or change playback speed below.';
    if(data.complete){const s=data.summary,n=v=>v===null?'—':v.toFixed(1);$('outcomes').innerHTML=`Parked <b>${s.parked} / ${s.drivers}</b><br>Mean search <b>${n(s.mean_search_s)} s</b><br>Mean walk <b>${n(s.mean_walk_m)} m</b><br>Mean intended-exit distance <b>${n(s.mean_exit_m)} m</b>`;}
  }catch(error){$('job-status').textContent=error.message;setPlaying(false);}finally{live.busy=false;}
}
async function submit(event) {
  event.preventDefault();$('run-button').disabled=true;
  try {
    const settings=settingsFromForm();
    const job=await api('/api/runs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settings)});
    while(true){const progress=await api('/api/runs/'+job.id);$('job-status').textContent=`${progress.status==='queued'?'Queued':'Simulating'}${progress.simulation_seconds?' · '+formatTime(progress.simulation_seconds)+' simulated':''}…`;
      if(progress.status==='failed')throw Error(progress.error);
      if(progress.status==='complete'){await loadRun(job.id);break;}
      await new Promise(resolve=>setTimeout(resolve,750));
    }
  }catch(error){$('job-status').textContent=error.message;}finally{$('run-button').disabled=false;}
}
async function init() {
  if(!C)throw Error('Cesium could not load. Internet access to cesium.com is needed for this preview.');
  state.scene=await api('/api/scene');createScene();window.PandaPlatform.attachViewer(viewer);loadContext().catch(error=>{$('map-status').textContent=error.message;});
  $('scenario').addEventListener('submit',submit);
  $('info-buttons').addEventListener('click',event=>{const button=event.target.closest('[data-mode]');if(!button)return;
    $('information').value=button.dataset.mode;$('info-help').textContent=infoText[button.dataset.mode];
    document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('selected',b===button));});
  $('occupancy').addEventListener('input',()=>{$('occupancy-value').textContent=$('occupancy').value+'%';});
  $('play').addEventListener('click',()=>{if(state.run&&state.time>=state.run.duration_s)state.time=0;setPlaying(!state.playing);});
  $('timeline').addEventListener('input',()=>{state.time=Number($('timeline').value);render();});
  $('reset-camera').addEventListener('click',()=>home());
  $('overhead-camera').addEventListener('click',()=>home(true));
  $('live-button').addEventListener('click',startLive);
  $('history').addEventListener('change',()=>loadRun($('history').value).catch(error=>{$('job-status').textContent=error.message;}));
  $('show-context').addEventListener('change',()=>state.context.forEach(m=>{m.show=$('show-context').checked;}));
  $('show-network').addEventListener('change',()=>state.networks.forEach(e=>{e.show=$('show-network').checked;}));
  $('download').addEventListener('click',async()=>{if(!state.run)return;const url=URL.createObjectURL(new Blob([JSON.stringify(state.run)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`panda-${state.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  await loadRun('baseline');requestAnimationFrame(tick);
}
init().catch(error=>{$('map-status').textContent=error.message;$('job-status').textContent=error.message;console.error(error);});
