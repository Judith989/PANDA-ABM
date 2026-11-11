/* Display adapter only: all decisions, claims and movement come from Python. */
const $ = id => document.getElementById(id);
const C = window.Cesium;
const state = {scene:null, run:null, id:null, time:0, playing:false, selected:null, live:null, slotEntities:new Map(), drivers:new Map(), parkedCars:new Map(), backgroundCars:new Map(), pedestrians:new Map(), context:[], networks:[]};
const draft={occupied:new Set(),closed:new Set(),schedule:[]};
let trajectoryEntity;
const infoText = {unaided:'Drivers find spaces by observing nearby bays as they drive.',aisle:'Drivers know how many usable free spaces are in each aisle, then search within it.',space:'Drivers know which individual spaces are free and can head toward one. Spaces are not reserved.'};
const colors = {free:'#65ac82',occupied:'#ce7950',blocked:'#89928b'};
let viewer, lastTick, appliedTime=-1;
let followController;
let currentEnvironment;
const modelNames = {cpt:'CPT',rum:'M1',deterministic:'M0'};
const esc = value => String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reasonLabel = value => ({following_vehicle:'Following a vehicle',junction_yield:'Yielding at a junction',downstream_queue:'Waiting for room beyond a junction',parking_maneuver:'Parking maneuver ahead',red_signal:'Red signal',stop_control:'Stop sign',pedestrian_crossing:'Pedestrians crossing',occupied_bay:'Occupied parking bay clearance',vehicle_clearance:'Vehicle footprint clearance',deadlock_release:'Passing a mutual blockage',spillback_from_next_segment:'Queue spilling back from the next segment',stall_limit:'Released after 90 s stopped',building_clearance:'Building clearance'}[value]??value??'—');
const formatTime = seconds => `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(Math.floor(seconds%60)).padStart(2,'0')}`;
async function api(url, options) {return window.PandaPlatform.api(url,options);}
function slotAngle(slot){return ((slot.heading_reference==='clockwise_from_north'?90-(slot.heading_deg??0):(slot.heading_deg??0))*Math.PI/180);}
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
const STREET_LIMITS={street_1h:60,street_2h:120,street_3h:180,street_4h:240};
function updatePolicyOptions(){
  // Street-limit policies only change spaces classified as on-street parking.
  const street=(state.scene?.config.slots??[]).filter(s=>s.parking_kind==='on_street'&&!s.is_unavailable&&!s.is_blocked);
  const limits=new Set(street.map(s=>s.time_limit_minutes??null));
  for(const option of $('parking-policy').options){
    const minutes=STREET_LIMITS[option.value];if(minutes==null)continue;
    const same=street.length&&limits.size===1&&limits.has(minutes);
    option.disabled=!street.length;
    option.textContent=`${minutes/60} hour${minutes>60?'s':''} on street spaces${!street.length?' · no street spaces in this layout':same?' · same as configured here':''}`;
  }
  if($('parking-policy').selectedOptions[0]?.disabled)$('parking-policy').value='configured';
}
function sample(track,t) {
  // Through vehicles waiting outside the network have no samples until admitted.
  if(!track.samples.length)return {x:0,y:0,direction:[0,0],state:'not_arrived',space:null,search:0};
  const i=lastAt(track.samples,t),a=track.samples[i],b=track.samples[i+1];
  const p=window.PandaMotion.interpolate(a,b,t,state.run?.aisle_edges??[]);
  return {...p,state:a[3],space:a[4],search:a[5]};
}
function home(overhead=false) {
  followController?.stop();$('follow-driver').checked=false;$('camera-follow-status').textContent='Camera follow is off.';
  const slots=state.scene.config.slots,xs=slots.map(s=>s.local_x_m),ys=slots.map(s=>s.local_y_m),x=(Math.min(...xs)+Math.max(...xs))/2,y=(Math.min(...ys)+Math.max(...ys))/2;
  const radius=Math.max(40,Math.hypot(Math.max(...xs)-Math.min(...xs),Math.max(...ys)-Math.min(...ys))/2+25);
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(local(x,y,0),radius),{offset:new C.HeadingPitchRange(0,overhead?-Math.PI/2:-Math.PI/3,radius*(overhead?2.4:2.7)),duration:1});
}
function slotColor(slot,occupied) {return C.Color.fromCssColorString(slot.is_blocked||slot.is_unavailable?colors.blocked:occupied?colors.occupied:colors.free).withAlpha(.85);}
function parkingModules(config){
  const groups=new Map();
  for(const slot of config.slots??[]){const id=slot.module??slot.module_id;if(!id?.startsWith('Parking_Module_'))continue;
    if(!groups.has(id))groups.set(id,{id,letter:id.slice('Parking_Module_'.length),slots:[]});groups.get(id).slots.push(slot);}
  return [...groups.values()].sort((a,b)=>a.id.localeCompare(b.id)).map(g=>{const usable=g.slots.filter(s=>!s.is_unavailable&&!s.is_blocked),points=usable.length?usable:g.slots;return {...g,name:'Module '+g.letter,usable:usable.length,x:points.reduce((n,s)=>n+s.local_x_m,0)/points.length,y:Math.max(...points.map(s=>s.local_y_m))+5};});
}
function showModuleLabels(){
  state.moduleLabels=[];const groups=parkingModules(state.scene.config);
  $('module-list-panel').hidden=!groups.length;$('show-module-labels').disabled=!groups.length;
  $('module-list').innerHTML=groups.map(g=>`<button type="button" class="segment-link" data-module="${esc(g.id)}">${esc(g.name)} · ${g.usable} usable / ${g.slots.length} records</button>`).join('<br>');
  for(const group of groups)state.moduleLabels.push(viewer.entities.add({id:'module:'+group.id,name:group.name,position:local(group.x,group.y,2),show:$('show-module-labels').checked,label:{text:group.letter,font:'bold 16px sans-serif',fillColor:C.Color.WHITE,showBackground:true,backgroundColor:C.Color.fromCssColorString('#245b54'),pixelOffset:new C.Cartesian2(0,-10),disableDepthTestDistance:Infinity}}));
}
function focusParkingModule(id){
  const group=parkingModules(state.scene.config).find(g=>g.id===id);if(!group)return;
  $('follow-driver').checked=false;updateCameraFollow();
  for(const item of state.segmentHighlights??[])viewer.entities.remove(item);
  const slots=group.slots.filter(s=>!s.is_unavailable&&!s.is_blocked),points=slots.length?slots:group.slots;
  const x0=Math.min(...points.map(s=>s.local_x_m))-3,x1=Math.max(...points.map(s=>s.local_x_m))+3,y0=Math.min(...points.map(s=>s.local_y_m))-3,y1=Math.max(...points.map(s=>s.local_y_m))+3;
  state.segmentHighlights=[viewer.entities.add({polyline:{positions:[[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]].map(p=>local(...p,.6)),width:5,material:C.Color.YELLOW}})];
  const radius=Math.max(25,Math.hypot(x1-x0,y1-y0)/2);viewer.camera.flyToBoundingSphere(new C.BoundingSphere(local((x0+x1)/2,(y0+y1)/2,0),radius),{offset:new C.HeadingPitchRange(0,-Math.PI/3,radius*2.5),duration:.7});
  $('inspection').textContent=`${group.name} · ${group.usable} usable spaces / ${group.slots.length} configured records · ${group.id}`;document.querySelector('.map-shell').scrollIntoView({behavior:'smooth',block:'center'});
}
function createScene() {
  viewer = new C.Viewer('cesiumContainer',{baseLayer:false,baseLayerPicker:false,terrainProvider:new C.EllipsoidTerrainProvider(),
    animation:false,timeline:false,geocoder:false,homeButton:false,sceneModePicker:true,navigationHelpButton:true,
    fullscreenButton:true,selectionIndicator:true,infoBox:false,shouldAnimate:false});
  followController=window.PandaFollowCamera.create(C,viewer,text=>{$('camera-follow-status').textContent=text;});
  viewer.camera.percentageChanged=.05;viewer.camera.changed.addEventListener(updateNearbyCarModels);
  const basemap=viewer.imageryLayers.addImageryProvider(new C.OpenStreetMapImageryProvider({url:'https://tile.openstreetmap.org/',maximumLevel:19}));
  basemap.show=!state.scene.config.meta.synthetic||state.scene.config.meta.show_basemap===true;
  viewer.scene.globe.baseColor=C.Color.fromCssColorString('#e3e8dc');
  viewer.scene.backgroundColor=C.Color.fromCssColorString('#edf1e9');
  viewer.scene.skyBox.show=false;viewer.scene.skyAtmosphere.show=false;viewer.scene.sun.show=false;viewer.scene.moon.show=false;
  viewer.scene.globe.enableLighting=false;
  for(const slot of state.scene.config.slots) {
    const x=slot.local_x_m,y=slot.local_y_m,angle=slotAngle(slot),l=(slot.length_m??4.9)/2,w=(slot.width_m??2.06)/2;
    const corners=[[-l,-w],[l,-w],[l,w],[-l,w]].map(([a,b])=>local(x+a*Math.cos(angle)-b*Math.sin(angle),y+a*Math.sin(angle)+b*Math.cos(angle)));
    const e=viewer.entities.add({id:'slot:'+slot.id,name:slot.id,
      polygon:{hierarchy:new C.PolygonHierarchy(corners),
        perPositionHeight:true,material:slotColor(slot,false),outline:false}});
    state.slotEntities.set(slot.id,{entity:e,slot,occupied:false});
  }
  const config=state.scene.config;
  showModuleLabels();
  const landmarks=[...(config.walmart_doors||[]).map((p,i)=>({...p,name:p.name??`Door ${i+1}`,color:'#163a34'})),
    ...(config.parking_lot_exits||config.entry_points||[]).map((p,i)=>({...p,name:`Entry / Exit ${i===0?'A':'B'}`,color:'#986326'}))];
  for(const p of landmarks) {
    const pos=p.local_x_m!==undefined?local(p.local_x_m,p.local_y_m,2):C.Cartesian3.fromDegrees(p.lon,p.lat,2);
    viewer.entities.add({id:'landmark:'+p.id,name:p.name,position:pos,
      point:{pixelSize:11,color:C.Color.fromCssColorString(p.color),outlineColor:C.Color.WHITE,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},
      label:{text:p.name,font:'bold 13px sans-serif',fillColor:C.Color.WHITE,showBackground:true,backgroundColor:C.Color.fromCssColorString(p.color),
        pixelOffset:new C.Cartesian2(0,-22),disableDepthTestDistance:Number.POSITIVE_INFINITY}});
  }
  viewer.screenSpaceEventHandler.setInputAction(click=>{
    const hits=viewer.scene.drillPick(click.position,12),editing=$('map-action').value!=='inspect';
    const hit=hits.find(h=>editing?h.id?.id?.startsWith('slot:'):['driver:','pedestrian:','parked:'].some(prefix=>h.id?.id?.startsWith(prefix)))??hits.find(h=>h.id?.id?.startsWith('slot:'))??hits[0];
    if(hit?.id?.id?.startsWith('module:')&&!editing){focusParkingModule(hit.id.id.slice(7));return;}
    if(hit&&hit.id){state.selected=hit.id.id.replace(/:car(:model)?$/,'');const [kind,id]=state.selected.split(':');if(['driver','parked','pedestrian'].includes(kind))$('driver-select').value=id;handleMapSelection();inspect();if(state.run&&!state.editingOccupancy)updateTraffic();}
  },C.ScreenSpaceEventType.LEFT_CLICK);
  home();
}
async function loadContext() {
  const a=state.scene.alignment,models=currentEnvironment?.models??[{url:'assets/parking_asphalt.glb'},{url:'assets/walmart_building.glb'}];
  $('show-context').disabled=!models.length;$('show-context').checked=!!models.length;
  if(!a||!models.length){$('alignment-note').textContent='No 3D context mesh is attached. Spaces and driving routes come from the environment JSON.';$('map-status').hidden=true;return;}
  $('alignment-note').textContent=a.context_note??(a.fit_rmse_m!=null?`${a.matched_ids.toLocaleString()} matched space IDs. Scene-fit RMS residual: ${a.fit_rmse_m.toFixed(2)} m. Slot markers use JSON coordinates.`:'User-aligned model. Coordinate and network checks do not establish survey accuracy.');
  const targetViewer=viewer;
  const enu=C.Transforms.eastNorthUpToFixedFrame(local(a.east_m,a.north_m,a.height_m));
  const rotation=C.Matrix4.fromRotationTranslation(C.Matrix3.fromRotationZ(a.rotation_radians));
  const transform=C.Matrix4.multiply(enu,rotation,new C.Matrix4());C.Matrix4.multiplyByUniformScale(transform,a.scale,transform);
  const results=await Promise.allSettled(models.map(async item=>{
    const model=await C.Model.fromGltfAsync({url:item.url,modelMatrix:transform,upAxis:C.Axis[a.up_axis??'Y'],forwardAxis:C.Axis[a.forward_axis??'X'],allowPicking:false});
    if(viewer!==targetViewer||targetViewer.isDestroyed()){model.destroy();return;}
    targetViewer.scene.primitives.add(model);state.context.push(model);return model;
  }));
  const failed=results.filter(r=>r.status==='rejected');
  if(failed.length){$('map-status').hidden=false;$('map-status').textContent='3D context failed to load. Check that the GLB contains supported embedded resources.';throw Error('A 3D model could not load. Check its format and retry.');}
  $('map-status').hidden=true;
}
async function reloadEnvironmentContext(item){
  state.scene.alignment=item.scene.alignment;
  for(const m of state.context)if(!m.isDestroyed())viewer.scene.primitives.remove(m);state.context=[];
  await loadContext();
}
async function applyEnvironment(item){
  setPlaying(false);await closeLive();
  if(viewer&&!viewer.isDestroyed())viewer.destroy();
  currentEnvironment=item;state.scene=item.scene;state.run=null;state.selected=null;state.time=0;$('congestion-legend').hidden=true;
  state.context=[];state.networks=[];state.segmentHighlights=[];state.roadEdges=[];state.slotEntities.clear();state.backgroundCars.clear();bayFits.clear();state.drivers.clear();state.parkedCars.clear();state.pedestrians.clear();trajectoryEntity=null;appliedTime=-1;
  state.previewPanels=null;state.editingOccupancy=false;draft.occupied.clear();draft.closed.clear();draft.schedule=[];
  createScene();window.PandaPlatform.attachViewer(viewer);updatePolicyOptions();
  document.querySelector('.site').textContent=item.name;$('environment-map-label').textContent=state.scene.config.meta.alignment_status==='provisional_satellite_simulation_variant'?'Satellite estimate · provisional':state.scene.config.meta.synthetic?'Synthetic layout · illustrative':'Configured lot geometry';document.querySelector('.map-caption b').textContent=state.scene.config.slots.length.toLocaleString()+' spaces';
  const usable=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
  const pedestrian=state.scene.config.pedestrian_network;$('traffic-enabled').disabled=!!pedestrian;if(pedestrian)$('traffic-enabled').checked=true;$('pedestrian-routing-note').textContent=pedestrian?`Walking network active. ${pedestrian.summary?.spaces_with_egress??'?'} bays have an egress connector; destination reachability varies. Disconnected spaces are excluded. Connections and entrances include estimates.`:'This imported environment has no walking network and uses straight-line walking.';
  $('free-count').max=usable;$('free-count').value=Math.min(5,usable);
  const net=state.scene.config.aisle_network;
  if(net)showNetwork(net.edges.map(([a,b])=>[net.nodes[a],net.nodes[b]]));
  beginOccupancyDraft();await loadContext();window.PandaEnvironments.select(item.key);
}
function showNetwork(edges) {
  $('driver-select').replaceChildren(new Option('Choose a driver',''),...(state.run?.tracks??[]).map(t=>new Option(t.id,t.id)));
  for(const e of state.networks)viewer.entities.remove(e);state.networks=[];
  const stalls=new Set(state.scene.config.slots.map(s=>`${s.local_x_m.toFixed(5)},${s.local_y_m.toFixed(5)}`));
  const key=p=>`${p[0].toFixed(5)},${p[1].toFixed(5)}`;
  state.roadEdges=edges.map(([a,b])=>({a,b,spur:stalls.has(key(a))||stalls.has(key(b))}));
  const lanes=state.run?.settings.traffic_enabled??$('traffic-enabled').checked;
  for(const edge of state.roadEdges){const {a,b,spur}=edge,length=Math.hypot(b[0]-a[0],b[1]-a[1]);if(length<1e-8)continue;
    const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2],aisles=state.run?.aisles??{};
    let best=8,key='cross_aisle';for(const [id,[p,q]] of Object.entries(aisles)){const dx=q[0]-p[0],dy=q[1]-p[1],f=Math.max(0,Math.min(1,((mid[0]-p[0])*dx+(mid[1]-p[1])*dy)/(dx*dx+dy*dy)));const d=Math.hypot(mid[0]-p[0]-f*dx,mid[1]-p[1]-f*dy);if(d<best){best=d;key=id;}}
    for(const offset of lanes&&!spur?[-1.2,1.2]:[0]){
      const shift=[(b[1]-a[1])/length*offset,-(b[0]-a[0])/length*offset];
      const entity=viewer.entities.add({polyline:{positions:[local(a[0]+shift[0],a[1]+shift[1],.14),local(b[0]+shift[0],b[1]+shift[1],.14)],width:spur?0.65:1.5,material:C.Color.fromCssColorString(spur?'#cbd4b7':'#71b8c4').withAlpha(spur?0.35:0.8)},show:$('show-network').checked});
      entity._aisleId=key;entity._segment=[a,b];entity._spur=spur;state.networks.push(entity);
    }
  }
}

function handleMapSelection(){
  if(!state.selected?.startsWith('slot:'))return;
  const id=state.selected.slice(5),item=state.slotEntities.get(id),mode=$('map-action').value;
  if(mode==='inspect')return;
  if(item.slot.is_blocked||item.slot.is_unavailable){$('job-status').textContent='This space is outside the usable inventory.';return;}
  const selected=mode==='occupied'?draft.occupied:draft.closed;
  selected.has(id)?selected.delete(id):selected.add(id);
  if(mode==='occupied'){state.editingOccupancy=true;setPlaying(false);$('supply-mode').value='pick';}
  updateDraft();
}
function updateDraft(){
  $('picked-count').textContent=`· ${draft.occupied.size} occupied, ${draft.closed.size} closed`;
  for(const [id,item] of state.slotEntities){item.entity.polygon.outline=draft.occupied.has(id)||draft.closed.has(id);item.entity.polygon.outlineColor=C.Color.fromCssColorString(draft.closed.has(id)?'#d41c46':'#00efff');}
  $('intervention-list').textContent=draft.schedule.length?draft.schedule.map(e=>`${e.time_s}s: ${e.action} ${e.space_ids.join(', ')}`).join(' · '):'No scheduled changes.';
  updateSupplyControls();
  if(state.editingOccupancy)renderOccupancyDraft();
}
function updateSupplyControls(){
  const mode=$('supply-mode').value,percentage=mode==='percentage';
  $('occupancy').hidden=!percentage;$('occupancy').disabled=!percentage;
  $('free-count').disabled=mode!=='count';$('free-count').hidden=mode!=='count';$('free-count').required=mode==='count';
  $('free-count-label').hidden=mode!=='count';$('picked-count').hidden=mode!=='pick';
  $('supply-count-label').textContent=mode==='pick'?'Selected spaces':'Empty spaces';
  const capacity=state.scene?.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length??1106;
  const free=mode==='pick'?capacity-draft.occupied.size:Number($('free-count').value);
  $('occupancy-value').textContent=percentage?$('occupancy').value+'%':(100*(1-free/capacity)).toFixed(2)+'%';
  const requested=capacity*Number($('occupancy').value)/100,floor=Math.floor(requested);
  const occupied=percentage?(requested-floor===.5?(floor%2===0?floor:floor+1):Math.round(requested)):mode==='pick'?draft.occupied.size:capacity-free;
  $('initial-supply-summary').textContent=`${occupied} initially occupied · ${capacity-occupied} empty · ${capacity} usable spaces${draft.closed.size?' · '+draft.closed.size+' closed (tracked separately)':''}.`;
}
function beginOccupancyDraft(){
  if(!state.editingOccupancy)state.previewPanels=Object.fromEntries(['chart','outcomes','verification','time','duration'].map(id=>[id,$(id).innerHTML]));
  setPlaying(false);followController?.stop();$('follow-driver').checked=false;$('camera-follow-status').textContent='Camera follow is off.';draft.occupied.clear();state.editingOccupancy=true;
  $('play').disabled=true;$('timeline').disabled=true;
  $('supply-mode').value='pick';$('map-action').value='occupied';
  updateDraft();
}
function endOccupancyDraft(){
  state.editingOccupancy=false;$('play').disabled=false;$('timeline').disabled=false;syncPauseButton();
  if(state.previewPanels){for(const [id,html] of Object.entries(state.previewPanels))$(id).innerHTML=html;state.previewPanels=null;}
  $('map-action').value='inspect';appliedTime=-1;
  if(state.run){$('run-title').textContent=state.run.live?'Live parking simulation':'Saved replay';$('view-mode').textContent=state.run.live?'LIVE SIMULATION · CESIUMJS 3D':'SAVED REPLAY · CESIUMJS 3D';$('run-description').textContent='Current recording. Start a new simulation to apply the configured initial occupancy.';}
}
// Model footprints (width, length in metres) measured from the bundled GLBs.
const VEHICLE_SIZE={compact:[1.85,3.93],sedan:[1.95,4.58],suv:[2.07,4.79],van:[2.13,5.19],truck:[2.15,5.48]};
// Uniform scale so a parked model keeps clear of neighbouring and opposite bays:
// at least 0.3 m between side-by-side cars and 0.6 m between opposite cars.
// Where a layout's opposite bays overlap (the original Walmart estimate puts
// head-to-head bay centres ~3.1 m apart for 4.9-m bays), each car is given its
// own half of the shared strip and shifted outward; display only.
const bayFits=new Map();
function bayFit(slot){
  let fit=bayFits.get(slot);if(fit)return fit;
  const length=slot.length_m??4.9,angle=slotAngle(slot),u=[Math.cos(angle),Math.sin(angle)];let gap=Infinity,side=0;
  for(const other of state.scene.config.slots){
    if(other===slot||other.is_unavailable)continue;
    const dx=other.local_x_m-slot.local_x_m,dy=other.local_y_m-slot.local_y_m,along=dx*u[0]+dy*u[1];
    if(Math.abs(-dx*u[1]+dy*u[0])<1&&Math.abs(along)<gap){gap=Math.abs(along);side=Math.sign(along);}
  }
  const overlap=Math.max(0,length-gap),shift=-side*overlap/4;
  fit={length:length-overlap/2,x:slot.local_x_m+u[0]*shift,y:slot.local_y_m+u[1]*shift};bayFits.set(slot,fit);return fit;
}
function parkedScale(kind,slot){
  const [w,l]=VEHICLE_SIZE[kind]??VEHICLE_SIZE.sedan;
  return Math.min(1,((slot.width_m??2.06)-.3)/w,(bayFit(slot).length-.6)/l);
}
// A parked car in every occupied bay that no simulated driver is shown in
// (initial occupancy, background vehicles and the manual selection draft).
// Near the camera it is the real vehicle model; beyond 600 m a car-sized box
// (batched by Cesium) keeps a full lot cheap to draw.
const BACKGROUND_KINDS=['sedan','suv','compact','sedan','van','suv','truck','sedan'];
const BACKGROUND_COLORS=['#d8dcdf','#2e3236','#878d93','#7c2228','#26487c','#ebe8e0','#4b5a3b','#a3a7ab','#5a3d2b'];
// Real models are created only for cars near the camera and released when the
// camera moves away; every parked car also has a cheap batched box for the far view.
const MODEL_RANGE_M=200,MODEL_RELEASE_M=300,FAR=new C.DistanceDisplayCondition(MODEL_RANGE_M,Number.MAX_VALUE);
function showBackgroundCars(occupied,driverSlots=new Set()){
  for(const [id,item] of state.slotEntities){
    const visible=occupied.has(id)&&!driverSlots.has(id)&&!item.slot.is_unavailable&&!item.slot.is_blocked;
    let car=state.backgroundCars.get(id);
    if(!visible){if(car)car.show=false;continue;}
    if(!car){
      let hash=0;for(const c of id)hash=(hash*31+c.charCodeAt(0))>>>0;
      // Background vehicles use types that fit the bay with little shrinking.
      const slot=item.slot,fitting=BACKGROUND_KINDS.filter(k=>parkedScale(k,slot)>=.8),kinds=fitting.length?fitting:['compact'];
      const kind=kinds[hash%kinds.length],scale=parkedScale(kind,slot),[w,l]=VEHICLE_SIZE[kind],fit=bayFit(slot);
      const color=C.Color.fromCssColorString(BACKGROUND_COLORS[(hash>>>4)%BACKGROUND_COLORS.length]),centre=local(fit.x,fit.y,.06+.7*scale);
      car=viewer.entities.add({id:'slot:'+id+':car',name:id,position:centre,orientation:C.Transforms.headingPitchRollQuaternion(centre,new C.HeadingPitchRoll(-slotAngle(slot),0,0)),
        box:{dimensions:new C.Cartesian3(w*scale,l*scale,1.4*scale),material:color,distanceDisplayCondition:FAR}});
      car.vehicle={kind,scale,color,x:fit.x,y:fit.y,angle:slotAngle(slot),anchor:local(fit.x,fit.y,0)};
      state.backgroundCars.set(id,car);
    }
    car.show=true;
  }
  updateNearbyCarModels();
}
function updateNearbyCarModels(){
  if(!viewer||viewer.isDestroyed())return;
  const eye=viewer.camera.positionWC;
  for(const [id,car] of state.backgroundCars){
    const distance=C.Cartesian3.distance(eye,car.vehicle.anchor),child=car.modelEntity;
    if(car.show&&distance<MODEL_RANGE_M&&!child){
      const v=car.vehicle,position=local(v.x,v.y,.06);
      car.modelEntity=viewer.entities.add({id:'slot:'+id+':car:model',name:id,parent:car,position,orientation:C.Transforms.headingPitchRollQuaternion(position,new C.HeadingPitchRoll(-v.angle,0,0)),
        model:{uri:`assets/vehicles/${v.kind}.glb`,scale:v.scale,runAnimations:false,distanceDisplayCondition:new C.DistanceDisplayCondition(0,MODEL_RANGE_M),
          color:v.color,colorBlendMode:C.ColorBlendMode.MIX,colorBlendAmount:.55}});
    }else if(child&&(!car.show||distance>MODEL_RELEASE_M)){viewer.entities.remove(child);car.modelEntity=null;}
  }
}
// Cars in lot = cars already parked at the start (or background) + arriving drivers parked now.
function showLotCount(total,initial,capacity){
  $('occupied').textContent=total.toLocaleString();
  $('occupied-detail').textContent=`${(100*total/capacity).toFixed(1)}% of ${capacity.toLocaleString()} spaces · ${initial.toLocaleString()} already there + ${(total-initial).toLocaleString()} arrivals`;
}
function renderOccupancyDraft(){
  syncPauseButton();
  for(const [id,item] of state.slotEntities){
    item.occupied=draft.occupied.has(id);item.closed=draft.closed.has(id);
    item.entity.polygon.material=item.closed?C.Color.fromCssColorString('#a92259').withAlpha(.9):slotColor(item.slot,item.occupied);
  }
  for(const e of [...state.drivers.values(),...state.parkedCars.values(),...state.pedestrians.values()])e.show=false;
  showBackgroundCars(draft.occupied);$('congestion-legend').hidden=true;
  for(const e of state.networks){e.polyline.width=1;e.polyline.material=C.Color.fromCssColorString('#a6bda1').withAlpha(.6);}
  if(trajectoryEntity){viewer.entities.remove(trajectoryEntity);trajectoryEntity=null;}
  const capacity=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
  showLotCount(draft.occupied.size,draft.occupied.size,capacity);
  for(const id of ['parked','searching','abandoned'])$(id).textContent='0';
  $('view-mode').textContent='INITIAL OCCUPANCY · MAP SELECTION';
  $('run-title').textContent='Choose initially occupied spaces';
  $('run-description').textContent=`${draft.occupied.size} occupied / ${capacity} usable spaces. Unselected spaces start empty.`;
  $('job-status').textContent='Initial layout preview. Click to occupy a space; click again to clear it. Start a simulation to apply this layout.';
  $('supply-status').textContent=`${draft.occupied.size} initially occupied; ${capacity-draft.occupied.size} initially empty (including closed spaces).`;
  $('traffic-status').textContent='No simulation is running in this layout preview.';$('congestion-episodes').textContent='';
  $('outcomes').textContent='Start a simulation to calculate outcomes for this initial layout.';
  $('chart').innerHTML='';$('verification').textContent='Initial layout preview. Only selected spaces will start occupied.';
  $('time').textContent='00:00';$('duration').textContent='00:00';$('timeline').value=0;
}
function telemetryAt(t){
  const rows=state.run?.traffic_samples??[];
  return rows.length?rows[lastAt(rows.map(r=>[r.time_s]),t)]:null;
}
function segmentInfo(id,config=state.scene?.config,labels=state.run?.segment_labels){
  let info=labels?.[id]??config?.aisle_network?.segment_labels?.[id];
  // Legacy downtown recordings used this same fixed block grid, without labels.
  if(!info&&config?.meta?.lot_name?.startsWith('Downtown Laramie')){
    const roads=['South 1st Street','South 2nd Street','South 3rd Street'],cross=['East Ivinson Avenue','East Grand Avenue','East Garfield Street'];
    let m=id.match(/^street_([0-2])_([01])$/);if(m)info={road_name:roads[+m[1]],from:cross[+m[2]],to:cross[+m[2]+1]};
    m=id.match(/^cross_([0-2])_([01])$/);if(m)info={road_name:cross[+m[1]],from:roads[+m[2]],to:roads[+m[2]+1]};
    if(id==='lot_north'||id==='lot_south')info={road_name:'Off-street parking lot',label:'Off-street lot — '+id.slice(4)+' circulation aisle'};
  }
  if(!info&&/^aisle_\d+$/.test(id)){const members=[...new Set((config?.slots??[]).filter(s=>config?.aisle_network?.space_access?.[s.id]?.aisle===id).map(s=>(s.module??s.module_id??'').replace('Parking_Module_','Module ')))].filter(Boolean).sort();const name='Parking aisle '+String(Number(id.slice(6))+1).padStart(2,'0');info={road_name:name,modules:members.join(', '),label:name+(members.length?' — serves '+members.join(', '):'')};}
  if(!info)return {id,road_name:id==='cross_aisle'?'Unassigned connecting road':id,label:id==='cross_aisle'?'Connecting road — location not assigned':id};
  return {...info,id,label:info.label??[info.road_name,[info.from,info.to].filter(Boolean).join(' to ')].filter(Boolean).join(' — ')};
}
window.PandaSegmentInfo=segmentInfo;
function segmentLink(id){return `<button type="button" class="segment-link" data-traffic-segment="${esc(id)}" title="Highlight on map · ${esc(id)}">${esc(segmentInfo(id).label)}</button>`;}
function focusTrafficSegment(id){
  const config=state.scene.config,net=config.aisle_network;let ends=state.run?.aisles?.[id];
  if(!ends&&net?.aisles?.[id])ends=net.aisles[id].map(n=>net.nodes[n]);
  const info=segmentInfo(id);$('inspection').textContent=info.label+' · ID: '+id;
  if(!ends){$('inspection').textContent+=' · No mapped segment endpoints are recorded.';return;}
  $('follow-driver').checked=false;updateCameraFollow();
  for(const item of state.segmentHighlights??[])viewer.entities.remove(item);
  const points=ends.map(p=>local(p[0],p[1],.5)),mid=ends[0].map((v,i)=>(v+ends[1][i])/2);
  state.segmentHighlights=[viewer.entities.add({polyline:{positions:points,width:8,material:C.Color.YELLOW}}),viewer.entities.add({position:local(mid[0],mid[1],4),label:{text:info.label,font:'bold 14px sans-serif',fillColor:C.Color.WHITE,showBackground:true,backgroundColor:C.Color.BLACK.withAlpha(.8),disableDepthTestDistance:Infinity}})];
  const radius=Math.max(45,Math.hypot(ends[0][0]-ends[1][0],ends[0][1]-ends[1][1]));
  viewer.camera.flyToBoundingSphere(new C.BoundingSphere(local(mid[0],mid[1],0),radius),{offset:new C.HeadingPitchRange(0,-Math.PI/3,radius*2),duration:.7});
  document.querySelector('.map-shell').scrollIntoView({behavior:'smooth',block:'center'});
}
function updateTraffic(){
  const run=state.run,frame=telemetryAt(state.time),traffic=frame?.traffic;
  const supply=frame?.supply;
  if(supply)$('supply-status').textContent=`${supply.free} empty and open · ${supply.occupied} occupied · ${supply.closed} closed (${supply.closed_occupied} occupied). Occupancy uses the fixed ${supply.usable_inventory}-space usable inventory.`;
  else $('supply-status').textContent='';
  if(trajectoryEntity)viewer.entities.remove(trajectoryEntity);trajectoryEntity=null;
  const selected=window.PandaFollowCamera.selectedDriver($('driver-select').value,state.selected),track=run.tracks.find(tr=>tr.id===selected);
  if(track&&$('show-trajectory').checked){
    const points=track.samples.filter(p=>p[0]<=state.time&&p[3]!=='not_arrived').flatMap(p=>(p[6]?.length?p[6]:[[p[1],p[2]]]).map(q=>local(q[0],q[1],1.8)));
    if(points.length>1)trajectoryEntity=viewer.entities.add({polyline:{positions:points,width:4,material:C.Color.YELLOW}});
  }
  if(!traffic?.enabled){$('congestion-legend').hidden=true;$('traffic-status').textContent='Traffic interactions are disabled in this simulation.';$('congestion-episodes').textContent='';return;}
  const queue=Object.values(traffic.queues).reduce((a,b)=>a+b,0);
  const ranked=Object.entries(traffic.aisle_delay_s).sort((a,b)=>b[1]-a[1]);
  $('traffic-status').textContent=`${queue} vehicles currently queued · ${traffic.cumulative_delay_s.toFixed(1)} vehicle-seconds of traffic delay · ${(traffic.jam_episodes??[]).length} sustained multi-vehicle jams · ${traffic.episodes.length} delay episodes including single vehicles`;
  const through=frame?.through_traffic;if(through&&through.level!=='off')$('traffic-status').textContent+=` · through traffic: ${through.active} moving, ${through.waiting_entry} waiting outside, ${through.completed} completed`;
  $('congestion-episodes').innerHTML=jamReport(traffic)+'<p><b>Aisles with most delay</b></p>'+ranked.slice(0,5).map(([id,delay])=>`<div>${segmentLink(id)} · ${delay.toFixed(1)} vehicle-seconds · peak queue ${traffic.aisle_peak_queue[id]??0}</div>`).join('');
  colourRoads(traffic,frame);
}
// Road colours use the model's jam definition: at least two traffic-constrained
// vehicles below 0.5 m/s in the same aisle for at least 5 s.
const SLOWED_VEHICLE_S=30,ROAD_STYLE={jam:['#a02cff',5],earlier:['#cfa8f0',3.5],slowed:['#f2d24c',3],none:['#cfd6d1',1]};
function pointToSegment(p,a,b){const dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy,f=l?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/l)):0;return Math.hypot(p[0]-a[0]-f*dx,p[1]-a[1]-f*dy);}
// Jam report: where, when, how long, how many vehicles and the root cause (what held
// the front of the queue). Releases are stuck vehicles let through by the model.
function jamReport(traffic){
  const jams=traffic.jam_episodes??[],releases=traffic.deadlock_releases??[];
  if(!jams.length)return '<p><b>Jams</b></p><p class="help">No jams so far: no aisle has held two or more queued vehicles for 5 seconds.</p>';
  const roots=e=>Object.entries(e.root_cause_seconds??{}).sort((a,b)=>b[1]-a[1]);
  const cause=e=>{const r=roots(e),total=r.reduce((n,[,v])=>n+v,0);return r.length?r.map(([k,v])=>`${esc(reasonLabel(k))}${r.length>1?' '+Math.round(100*v/total)+'%':''}`).slice(0,2).join(', '):esc(Object.keys(e.causes??{}).map(reasonLabel).join(', '))};
  const byCause={};for(const e of jams){const top=roots(e)[0]?.[0]??'unknown';byCause[top]=(byCause[top]??0)+e.duration_s;}
  const durations=jams.map(e=>e.duration_s),ongoing=jams.filter(e=>e.end_s==null).length;
  const freed=e=>releases.filter(r=>r.aisle===e.aisle&&r.time_s>=e.start_s&&r.time_s<=(e.end_s??Infinity)).length;
  return `<p><b>Jams: ${jams.length}</b> (${ongoing} ongoing) · longest ${Math.max(...durations).toFixed(0)} s · average ${(durations.reduce((a,b)=>a+b,0)/jams.length).toFixed(0)} s</p>`
    +`<p class="help">Jam time by root cause: ${Object.entries(byCause).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`${esc(reasonLabel(k))} ${v.toFixed(0)} s`).join(' · ')}</p>`
    +[...jams].reverse().slice(0,15).map(e=>{const n=freed(e);return `<div class="jam-row">${segmentLink(e.aisle)} · ${formatTime(e.start_s)}–${e.end_s==null?'<b>ongoing</b>':formatTime(e.end_s)} · lasted ${e.duration_s.toFixed(0)} s · up to ${e.peak_queue} vehicles · cause: ${cause(e)}${n?` · ${n} stuck vehicle${n>1?'s':''} let through`:''}</div>`;}).join('');
}
function colourRoads(traffic,frame){
  const t=state.time,jams=traffic.jam_episodes??[],on=$('show-congestion').checked;
  const now=new Set(jams.filter(e=>e.start_s<=t&&(e.end_s==null||e.end_s>=t)).map(e=>e.aisle));
  const earlier=new Set(jams.filter(e=>e.end_s!=null&&e.end_s<t).map(e=>e.aisle));
  // Locate current jams by the queued vehicles themselves, not the whole aisle group.
  const queued=[];
  for(const [id,view] of Object.entries(frame?.drivers??{})){
    if(!view.reason||view.speed_m_s>=.5||!now.has(view.aisle))continue;
    const track=state.run.tracks.find(x=>x.id===id);if(!track?.samples.length)continue;
    const p=sample(track,t);queued.push({aisle:view.aisle,point:[p.x,p.y]});
  }
  const located=new Set(queued.map(q=>q.aisle));
  let shown=false;
  for(const e of state.networks){
    const id=e._aisleId;let level='none';
    if(on&&!e._spur){
      const near=queued.some(q=>q.aisle===id&&pointToSegment(q.point,...e._segment)<6);
      if(near||(now.has(id)&&!located.has(id)&&id!=='cross_aisle'))level='jam';
      else if(id!=='cross_aisle'&&earlier.has(id))level='earlier';
      else if(id!=='cross_aisle'&&(traffic.aisle_delay_s[id]??0)>=SLOWED_VEHICLE_S)level='slowed';
    }
    shown||=level!=='none';
    const [colour,width]=ROAD_STYLE[level];
    e.polyline.width=e._spur?0.65:width;
    e.polyline.material=C.Color.fromCssColorString(e._spur?'#cbd4b7':colour).withAlpha(e._spur?.35:.85);
  }
  $('congestion-legend').hidden=!shown;
}
function downloadCongestion(){
  const traffic=telemetryAt(state.time)?.traffic??state.run?.traffic;
  if(!traffic?.enabled){$('job-status').textContent='Start a traffic-enabled simulation to record congestion.';return;}
  const fields=['minimum_queued_vehicles','aisle','road_name','served_modules','segment_from','segment_to','segment_label','start_s','end_s','duration_s','peak_queue','multi_vehicle_queue','queued_vehicle_delay_s','following_vehicle_active_s','junction_yield_active_s','downstream_queue_active_s','parking_maneuver_active_s','red_signal_active_s','stop_control_active_s','pedestrian_crossing_active_s','occupied_bay_active_s','vehicle_clearance_active_s','building_clearance_active_s','cause_vehicle_seconds'];
  const quote=v=>`"${String(v??'').replaceAll('"','""')}"`;
  const rows=(traffic.jam_episodes??traffic.episodes).map(e=>[e.minimum_queued_vehicles??1,e.aisle,segmentInfo(e.aisle).road_name,segmentInfo(e.aisle).modules,segmentInfo(e.aisle).from,segmentInfo(e.aisle).to,segmentInfo(e.aisle).label,e.start_s,e.end_s,e.duration_s,e.peak_queue,e.peak_queue>=2,e.queued_vehicle_delay_s,...['following_vehicle','junction_yield','downstream_queue','parking_maneuver','red_signal','stop_control','pedestrian_crossing','occupied_bay','vehicle_clearance','building_clearance'].map(k=>e.cause_active_seconds?.[k]??''),JSON.stringify(e.cause_vehicle_seconds??{})]);
  const text=[fields,...rows].map(row=>row.map(quote).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=`panda-congestion-${state.id}-${Math.floor(state.time)}s.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function refreshHistory(selected) {
  const runs=await api('/api/runs');
  $('history').replaceChildren(...runs.filter(r=>r.status==='complete').map(r=>{
    const o=document.createElement('option');o.value=r.id;
    const s=r.settings,supply=s.initial_occupied_space_ids!=null?`${s.initial_occupied_space_ids.length} selected occupied`:s.initial_free_space_ids!=null?`${s.initial_free_space_ids.length} selected empty`:s.initial_free_count!=null?`${s.initial_free_count} empty`:`${Math.round(100*s.occupancy)}%`;
    o.textContent=`${r.id==='baseline'?'Reference':'Run '+r.id.slice(0,5)} · ${s.environment?.name??'Walmart original'} · ${modelNames[s.model]} / ${s.information} / ${supply}`;
    return o;
  }));
  if(selected)$('history').value=selected;
}
function createVehicleEntities(tracks,population){
  const types=new Map((population?.drivers??[]).map(d=>[d.attributes.driver_id,d.attributes.vehicle_type]));
  for(const track of tracks){
    const type=types.get(track.id)??'sedan',kind=['compact','sedan','suv','van','truck'].includes(type)?type:'sedan';
    track.vehicle_type=kind;
    if(!track.walking_intervals)track.walking_intervals=window.PandaPedestrians.legacyIntervals(track,state.scene.config.slots,state.scene.config.walmart_doors??[],1.4,state.scene.config.pedestrian_network);
    const graphics=()=>({uri:`assets/vehicles/${kind}.glb`,scale:1,runAnimations:false});
    state.drivers.set(track.id,viewer.entities.add({id:'driver:'+track.id,name:track.id,position:local(0,0,.06),
      model:graphics(),point:{pixelSize:9,color:C.Color.fromCssColorString('#a77b27'),outlineColor:C.Color.WHITE,outlineWidth:1.5,disableDepthTestDistance:Infinity}}));
    state.parkedCars.set(track.id,viewer.entities.add({id:'parked:'+track.id,name:track.id,show:false,position:local(0,0,.06),model:graphics()}));
    state.pedestrians.set(track.id,viewer.entities.add({id:'pedestrian:'+track.id,name:'Walking driver '+track.id,show:false,position:local(0,0,.03),model:{uri:'assets/pedestrian.glb',scale:1,runAnimations:false,color:C.Color.fromCssColorString('#16b5d0'),colorBlendMode:C.ColorBlendMode.MIX,colorBlendAmount:.6},point:{pixelSize:5,color:C.Color.fromCssColorString('#16b5d0'),outlineColor:C.Color.WHITE,outlineWidth:1,disableDepthTestDistance:Infinity}}));
  }
}
async function loadRun(id) {
  await closeLive();endOccupancyDraft();
  $('job-status').textContent='Loading replay…';setPlaying(false);
  const data=await api(`/api/runs/${id}/data`);
  const target=await window.PandaEnvironments.forRun(data.settings.environment);if(currentEnvironment?.key!==target.key)await applyEnvironment(target);endOccupancyDraft();
  state.run=data;state.id=id;state.time=0;state.selected=null;appliedTime=-1;
  for(const e of state.drivers.values())viewer.entities.remove(e);state.drivers.clear();
  for(const e of state.parkedCars.values())viewer.entities.remove(e);state.parkedCars.clear();
  for(const e of state.pedestrians.values())viewer.entities.remove(e);state.pedestrians.clear();
  createVehicleEntities(data.tracks,data.population);
  showNetwork(data.aisle_edges);
  $('timeline').max=data.duration_s;$('timeline').value=0;$('duration').textContent=formatTime(data.duration_s);
  $('run-title').textContent=id==='baseline'?'Saved reference run':'Your simulation';
  $('view-mode').textContent='SAVED REPLAY · CESIUMJS 3D';
  const s=data.settings,initialFree=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked&&!data.initial_occupied.includes(s.id)&&!(data.initial_closed??[]).includes(s.id)).length;$('run-description').textContent=`${modelNames[s.model]} / ${s.information} information / ${initialFree} initially empty and open / ${s.population_size} drivers / seed ${s.seed} / ${s.visit_profile??'baseline'} visits / ${s.parking_policy??'configured'} limits / through traffic ${s.through_traffic??'off'}`;
  const n=v=>v==null?'—':v.toFixed(1);
  $('outcomes').innerHTML=`Parked <b>${data.summary.parked} / ${data.summary.drivers}</b><br>Mean search <b>${n(data.summary.mean_search_s)} s</b><br>Mean walk <b>${n(data.summary.mean_walk_m)} m</b><br>Mean intended-exit distance <b>${n(data.summary.mean_exit_m)} m</b>`;
  if(data.summary.mean_entry_delay_s!=null)$('outcomes').innerHTML+=`<br>Mean entry wait <b>${n(data.summary.mean_entry_delay_s)} s</b><br>Arrival to parking / abandonment <b>${n(data.summary.mean_arrival_to_search_end_s)} s</b>`;
  $('verification').textContent=data.verification?`✓ ${data.verification.status}. Physical replay samples: 1 second.`:'Current Python ABM run · configuration, population and source hashes included in the download · physical samples: 1 second.';
  $('job-status').textContent='Replay ready. Press play or drag the timeline.';
  showSummary(data.summary,data.settings.simulation_duration_s!=null);chart();render();await refreshHistory(id);
}
function chart() {
  const run=state.run,cap=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
  const points=run.system.map(row=>`${45+row[0]/run.duration_s*600},${120-row[1]/cap*95}`).join(' ');
  $('chart').innerHTML=`<line x1="45" y1="120" x2="645" y2="120" stroke="#dce6da"/><line x1="45" y1="25" x2="645" y2="25" stroke="#edf1e9"/><text x="1" y="28" fill="#748575" font-size="13">100%</text><text x="15" y="123" fill="#748575" font-size="13">0%</text><polyline points="${points}" fill="none" stroke="#398565" stroke-width="3"/><line id="chart-cursor" x1="45" x2="45" y1="20" y2="125" stroke="#a8b938" stroke-width="2"/><text x="45" y="146" fill="#748575" font-size="12">00:00</text><text x="590" y="146" fill="#748575" font-size="12">${formatTime(run.duration_s)}</text>`;
}
function updateCameraFollow(){
  if(!followController)return;
  const id=window.PandaFollowCamera.selectedDriver($('driver-select').value,state.selected),track=state.run?.tracks.find(t=>t.id===id);
  if(!track){followController.update({enabled:$('follow-driver').checked,id:null});return;}
  const p=sample(track,state.time),person=state.pedestrians.get(id),car=state.parkedCars.get(id),moving=state.drivers.get(id);
  let actor=person?.show?person:car?.show?car:moving,kind=person?.show?'pedestrian':car?.show?'parked':'vehicle',position=actor?.position?.getValue(viewer.clock.currentTime),label=p.state.replaceAll('_',' ');
  if(p.state==='at_destination'){
    const door=state.scene.config.walmart_doors.find(d=>d.id===track.door);
    if(door)position=local(door.local_x_m,door.local_y_m,1);kind='destination';label='at '+(track.door??'destination').replace('door_','Door ');
  }
  followController.update({enabled:$('follow-driver').checked,id,kind,position,label,waiting:p.state==='not_arrived',finished:['left','abandoned'].includes(p.state),arrival:formatTime(track.arrival_s??0)});
}
function bringMapIntoView(){if($('follow-driver').checked)document.querySelector('.map-shell').scrollIntoView({behavior:'smooth',block:'center'});}
function render() {
  if(state.editingOccupancy){renderOccupancyDraft();return;}
  if(!state.run)return;
  const t=state.time,run=state.run,telemetry=telemetryAt(t),driverSlots=new Set(),moving=[];
  for(const track of run.tracks) {
    const p=sample(track,t),e=state.drivers.get(track.id);
    const parkedStage=['parked','walking_to_destination','at_destination','returning_to_vehicle'].includes(p.state);
    e.show=!['not_arrived','left','abandoned'].includes(p.state)&&!parkedStage;
    const walking=['walking_to_destination','returning_to_vehicle'].includes(p.state);
    if(e.show){
      const reported=telemetry?.drivers?.[track.id]?.display_offset_m??[0,0];
      const direction=Math.hypot(...p.direction)>1e-8?p.direction:[-reported[1],reported[0]];
      const offset=run.settings.traffic_enabled&&!walking?window.PandaMotion.laneOffset([p.x,p.y],direction,state.roadEdges??[]):[0,0];
      e.position=local(p.x+offset[0],p.y+offset[1],walking?1:.06);e.point.show=false;e.model.show=true;
      const norm=Math.hypot(...direction);
      if(!walking&&norm>1e-8)moving.push({id:track.id,x:p.x+offset[0],y:p.y+offset[1],direction:[direction[0]/norm,direction[1]/norm],type:track.vehicle_type,entity:e});
      e.point.color=C.Color.fromCssColorString(walking?'#a77b27':'#176ba4');
      if(Math.hypot(...direction)>1e-8)e.orientation=C.Transforms.headingPitchRollQuaternion(local(p.x,p.y,.06),new C.HeadingPitchRoll(-Math.atan2(direction[1],direction[0]),0,0));
      if(p.state==='parked'){const bay=state.slotEntities.get(p.space)?.slot;if(bay)e.orientation=C.Transforms.headingPitchRollQuaternion(local(p.x,p.y,.06),new C.HeadingPitchRoll(-slotAngle(bay),0,0));}
    }
    const person=state.pedestrians.get(track.id),pose=window.PandaPedestrians.position(track.walking_intervals,t,walking);
    person.show=Boolean(pose&&$('show-pedestrians').checked);
    if(person.show){
      person.position=local(pose.x,pose.y,.03);
      person.orientation=C.Transforms.headingPitchRollQuaternion(local(pose.x,pose.y,.03),new C.HeadingPitchRoll(-Math.atan2(pose.direction[1],pose.direction[0]),0,0));
      const swing=pose.leg.waiting?0:Math.sin(pose.elapsed_s*Math.PI*2)*.42;
      person.model.nodeTransformations=Object.fromEntries([['LeftLeg',swing],['RightLeg',-swing],['LeftArm',-swing*.8],['RightArm',swing*.8]].map(([name,angle])=>[name,new C.TranslationRotationScale(undefined,C.Quaternion.fromAxisAngle(C.Cartesian3.UNIT_X,angle))]));
    }
    const parked=state.parkedCars.get(track.id),slot=state.slotEntities.get(p.space);
    if(parked){parked.show=Boolean(slot&&parkedStage);if(parked.show)driverSlots.add(slot.slot.id);if(parked.show){const fit=bayFit(slot.slot);parked.position=local(fit.x,fit.y,.06);parked.model.scale=parkedScale(track.vehicle_type,slot.slot);parked.orientation=C.Transforms.headingPitchRollQuaternion(local(slot.slot.local_x_m,slot.slot.local_y_m,.06),new C.HeadingPitchRoll(-slotAngle(slot.slot),0,0));}}
  }
  // Draw overlapping vehicle bodies apart; display only, the simulation state is unchanged.
  if(moving.length>1){const shifted=window.PandaMotion.separate(moving);for(const v of moving){const q=shifted.get(v.id);if(q)v.entity.position=local(q[0],q[1],.06);}}
  updateCameraFollow();
  if(Math.floor(t)!==appliedTime) {
    appliedTime=Math.floor(t);
    const occupied=new Set(run.initial_occupied);
    const closed=new Set(run.initial_closed??[]);
    for(const event of run.interventions??[]){if(event.time_s>t)continue;for(const id of event.space_ids){if(event.action==='close')closed.add(id);if(event.action==='open')closed.delete(id);}}
    for(const [time,added,removed] of run.occupancy_changes){if(time>t)break;for(const id of added)occupied.add(id);for(const id of removed)occupied.delete(id);}
    for(const [id,item] of state.slotEntities){const taken=occupied.has(id);item.occupied=taken;item.closed=closed.has(id);item.entity.polygon.material=item.closed?C.Color.fromCssColorString('#a92259').withAlpha(.9):slotColor(item.slot,taken);}
    showBackgroundCars(occupied,driverSlots);
    const row=run.system[lastAt(run.system,t)];
    $('parked').textContent=row[3];$('searching').textContent=row[2];$('abandoned').textContent=row[4];
    const cap=state.scene.config.slots.filter(s=>!s.is_unavailable&&!s.is_blocked).length;
    showLotCount(occupied.size,occupied.size-driverSlots.size,cap);inspect();updateTraffic();
  }
  $('timeline').value=t;$('time').textContent=formatTime(t);
  const cursor=$('chart-cursor');if(cursor){const x=45+t/run.duration_s*600;cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);}
}
function inspect() {
  if(!state.selected||!state.run){$('inspection').textContent='Click a driver or a parking space on the map to inspect it.';return;}
  const [kind,id]=state.selected.split(':');
  if(kind==='driver'||kind==='parked'||kind==='pedestrian'){
    const track=state.run.tracks.find(x=>x.id===id);if(!track)return;
    const p=sample(track,state.time);
    $('inspection').innerHTML=`<b>${esc(id)}</b> · ${esc(p.state.replaceAll('_',' '))}<br>Destination: ${esc(track.door?.replace('door_','Door '))}<br>Intended exit: ${esc(track.intended_exit?.replace('exit_a','A').replace('exit_b','B'))}<br>Chosen space: ${esc(p.space)}<br>Elapsed search: ${p.search.toFixed(1)} s`;
    const view=telemetryAt(state.time)?.drivers?.[id];
    if(view)$('inspection').innerHTML+=`<br>Speed: ${view.speed_m_s.toFixed(2)} m/s · traffic delay: ${view.delay_s.toFixed(1)} s<br>Same-lane ahead: ${esc(view.ahead)} · behind: ${esc(view.behind)} · bumper gap: ${view.gap_m==null?'—':view.gap_m.toFixed(1)+' m'}<br>Stopping / slowing cause: ${esc(reasonLabel(view.reason))} · blocking vehicle: ${esc(view.blocker)}<br>Nearby moving vehicles: ${(view.nearby??[]).map(n=>`${esc(n.driver)} (${n.distance_m.toFixed(1)} m)`).join(', ')||'none'}<br>Last scan: ${view.observation_s??'—'} s · ${view.visible_count??0} visible spaces, ${view.visible_free_count??0} reported free locally<br>Last evaluated candidates: ${view.last_candidates.slice(0,20).map(esc).join(', ')||'none'}${view.candidate_count>20?' … (complete IDs in download)':''}`;
  }else if(kind==='slot'){
    const item=state.slotEntities.get(id),s=item.slot;
    $('inspection').innerHTML=`<b>${esc(id)}</b> · ${esc((s.module??s.module_id??'').replace('Parking_Module_','Module '))}<br> ${s.is_unavailable?'Unavailable':item.closed?'Closed':item.occupied?'Occupied':'Free'}${item.closed&&item.occupied?' (vehicle remains until departure)':''}<br>${(state.scene.config.walmart_doors??[]).map(p=>esc(p.name??p.id)+': '+(state.scene.config.pedestrian_network?(s.walking_distance_to_destinations_m?.[p.id]==null?'No walking route':Number(s.walking_distance_to_destinations_m[p.id]).toFixed(1)+' m walking'):Number(s['distance_to_'+p.id+'_m']).toFixed(1)+' m')).join('<br>')}<br>${(state.scene.config.exit_points??[]).map(p=>esc(p.name??p.id)+': '+Number(s['distance_to_'+p.id+'_m']).toFixed(1)+' m').join('<br>')}<br>Time limit: ${s.time_limit_minutes??'None configured'} min<br><span class="help">${state.scene.config.pedestrian_network?'Door distances follow the walking graph; vehicle-access distances are straight-line.':'Straight-line distances'}</span>`;
  }else $('inspection').textContent=id;
}
function syncPauseButton(){
  $('pause-live').disabled=!state.live||state.live.complete||state.pausing||state.editingOccupancy;
  $('pause-live').textContent=!state.live?'Pause simulation':state.live.complete?'Simulation ended':state.pausing?'Pausing…':state.playing?'Pause simulation':'Resume simulation';
}
function setPlaying(playing){state.playing=playing;$('play').textContent=playing?'Ⅱ':'▶';$('play').setAttribute('aria-label',playing?'Pause replay':'Play replay');lastTick=undefined;syncPauseButton();}
async function togglePlayback(){
  if(state.pausing)return;
  if(state.live&&!state.live.complete&&state.playing){
    const live=state.live;state.pausing=true;setPlaying(false);
    try{
      while(state.live===live&&live.busy)await new Promise(resolve=>setTimeout(resolve,25));
      if(state.live===live){state.time=state.run.duration_s;render();$('job-status').textContent=`Paused at ${formatTime(state.time)} simulated time. Resume continues the same simulation.`;}
    }finally{state.pausing=false;syncPauseButton();}
  }else{if(state.run&&state.time>=state.run.duration_s&&(!state.live||state.live.complete))state.time=0;setPlaying(!state.playing);}
}
function selectedDuration(){const value=$('simulation-duration').value;return value==='full'?null:value==='custom'?Math.round(Number($('custom-duration-value').value)*Number($('custom-duration-unit').value)):Number(value);}
// Custom durations: 10 s to 6 h in either unit.
function updateDurationLimits(){const unit=Number($('custom-duration-unit').value),input=$('custom-duration-value');input.min=unit===1?10:(10/60).toFixed(2);input.max=21600/unit;}
function showSummary(summary,windowed=false){
  const n=v=>v==null?'—':v.toFixed(1),denominator=windowed?summary.arrivals:summary.drivers;
  $('outcomes').innerHTML=`Parked <b>${summary.parked} / ${denominator}</b><br>${windowed?'Mean observed search':'Mean search'} <b>${n(summary.mean_search_s)} s</b><br>Mean walk <b>${n(summary.mean_walk_m)} m</b><br>Mean intended-exit distance <b>${n(summary.mean_exit_m)} m</b>`;
  if(windowed)$('outcomes').innerHTML+=`<br>Searches unfinished at cutoff <b>${summary.unfinished}</b><br>Abandoned <b>${summary.abandoned}</b><br>Not yet arrived <b>${summary.not_arrived}</b><p class="help">The cutoff ends observation. Unfinished searches are not abandonments. Parking counts use arrivals before the cutoff.</p>`;
  if(summary.mean_entry_delay_s!=null)$('outcomes').innerHTML+=`<br>Mean entry wait <b>${n(summary.mean_entry_delay_s)} s</b>`;
}
function tick(now){if(lastTick&&state.playing&&state.run){state.time=Math.min(state.run.duration_s,state.time+(now-lastTick)/1000*Number($('speed').value));render();if(state.time===state.run.duration_s&&(!state.live||state.live.complete))setPlaying(false);}if(state.live&&state.playing&&!state.live.complete&&!state.live.busy&&state.run.duration_s-state.time<Number($('speed').value)*1.5)pumpLive();lastTick=now;requestAnimationFrame(tick);}
function settingsFromForm(){const mode=$('supply-mode').value;return {model:$('model').value,information:$('information').value,occupancy:Number($('occupancy').value)/100,
  population_size:Number($('population').value),arrival_interval_s:Number($('arrivals').value),seed:Number($('seed').value),
  initial_free_count:mode==='count'?Number($('free-count').value):null,initial_free_space_ids:null,
  initial_occupied_space_ids:mode==='pick'?[...draft.occupied].sort():null,
  closed_space_ids:[...draft.closed].sort(),interventions:draft.schedule.map(e=>({...e,space_ids:[...e.space_ids]})),traffic_enabled:$('traffic-enabled').checked,simulation_duration_s:selectedDuration(),background_departures:$('background-departures').value,visit_profile:$('visit-profile').value,parking_policy:$('parking-policy').value,through_traffic:$('through-traffic').value,through_demand_s:Number($('through-demand').value),demand_duration_s:$('demand-duration').value==='count'?null:Number($('demand-duration').value),environment:currentEnvironment?.environment??null};}
async function closeLive(){$('pause-live').disabled=true;if(!state.live)return;const id=state.live.id;state.live=null;await api('/api/live/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'close'})}).catch(()=>{});}
function appendFrames(frames){
  const run=state.run;
  for(const frame of frames){
    for(let i=0;i<frame.vehicles.length;i++){
      const row=frame.vehicles[i],track=run.tracks.find(t=>t.id===row[0]);if(!track)continue;
      track.samples.push([frame.time_s,...row.slice(1)]);
      if(frame.walking_intervals?.[track.id])track.walking_intervals=frame.walking_intervals[track.id];
      if(frame.observations?.[track.id]){track.observations??=[];track.observations.push(frame.observations[track.id]);}
    }
    if(frame.added.length||frame.removed.length)run.occupancy_changes.push([frame.time_s,frame.added,frame.removed]);
    run.system.push(frame.system);run.duration_s=Math.max(1,frame.time_s);
    run.interventions=frame.interventions??run.interventions??[];
    run.traffic_samples??=[];run.traffic_samples.push({time_s:frame.time_s,drivers:frame.driver_views??{},traffic:frame.traffic,supply:frame.supply,through_traffic:frame.through_traffic});
    run.traffic=frame.traffic;run.through_traffic=frame.through_traffic;
  }
  $('timeline').max=run.duration_s;$('duration').textContent=formatTime(run.duration_s);chart();
}
async function startLive(){
  if(window.PandaEnvironments.isPending()){$('job-status').textContent='Confirm or cancel the environment preview first.';return;}
  if(!$('scenario').reportValidity())return;
  $('live-button').disabled=true;
  try{
    setPlaying(false);await closeLive();endOccupancyDraft();
    $('job-status').textContent='Starting a live Python simulation…';
    const live=await api('/api/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(settingsFromForm())});
    state.live={id:live.id,busy:false,complete:false};state.id=live.id;state.time=0;state.selected=null;appliedTime=-1;
    state.run={segment_labels:live.segment_labels??{},schema_version:1,settings:live.settings,population:live.population,source_sha256:live.source_sha256,initial_occupied:live.initial_occupied,
      tracks:live.tracks,occupancy_changes:[],system:[],aisle_edges:live.aisle_edges,aisles:live.aisles,initial_closed:live.frame.supply.closed_space_ids,traffic_samples:[],duration_s:1,live:true};
    for(const e of state.drivers.values())viewer.entities.remove(e);state.drivers.clear();
    for(const e of state.parkedCars.values())viewer.entities.remove(e);state.parkedCars.clear();
  for(const e of state.pedestrians.values())viewer.entities.remove(e);state.pedestrians.clear();
    createVehicleEntities(live.tracks,live.population);
    appendFrames([live.frame]);showNetwork(live.aisle_edges);
    $('view-mode').textContent='LIVE SIMULATION · CESIUMJS 3D';$('run-title').textContent='Live parking simulation';
    const s=live.settings;$('run-description').textContent=`${modelNames[s.model]} / ${s.information} / ${s.population_size} drivers / ${live.frame.supply.free} initially empty and open / seed ${s.seed}${s.simulation_duration_s!=null?' / '+s.simulation_duration_s/60+'-minute window':''} / ${s.visit_profile??'baseline'} visits / ${s.parking_policy??'configured'} limits / through traffic ${s.through_traffic??'off'}`;
    $('outcomes').textContent='Simulation in progress. Results will appear when the selected window or full-trip simulation ends.';
    $('verification').textContent='Live Python ABM. Supply changes apply at the current engine time and are recorded. Traffic-enabled runs use an experimental kinematic queue model; archived paper results retain independent movement.';
    render();setPlaying(true);await pumpLive();
  }catch(error){$('job-status').textContent=error.message;}finally{$('live-button').disabled=false;}
}
async function pumpLive(){
  const live=state.live;if(!live||live.busy)return;live.busy=true;
  try{
    const data=await api('/api/live/'+live.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds:1})});
    if(state.live!==live)return;appendFrames(data.frames);live.complete=data.complete;state.run.summary=data.summary;state.run.termination_reason=data.termination_reason;if(data.cutoff_statuses)state.run.cutoff_statuses=data.cutoff_statuses;
    const limit=state.run.settings.simulation_duration_s;
    $('simulation-window-status').textContent=`Simulation clock ${formatTime(data.time_s)}${limit==null?' · full trips':' / '+formatTime(limit)+' limit'}`;
    if(!state.pausing)$('job-status').textContent=data.complete?(data.termination_reason==='time_limit'?'Selected simulation window reached. Unfinished searches remain separate from abandonments.':'Live simulation complete. You can replay or download this run.'):'Live Python model · '+formatTime(data.time_s)+' simulated · pause or change playback speed below.';
    if(data.complete){showSummary(data.summary,limit!=null);syncPauseButton();}

  }catch(error){$('job-status').textContent=error.message;setPlaying(false);}finally{live.busy=false;}
}
async function intervene(action){
  if(!state.live||state.live.complete){$('job-status').textContent='Start a live simulation first.';return;}
  if(!state.selected?.startsWith('slot:')){$('job-status').textContent='Inspect a usable parking space first.';return;}
  const wasPlaying=state.playing;setPlaying(false);
  try{while(state.live?.busy)await new Promise(r=>setTimeout(r,50));if(!state.live)return;
    const response=await api('/api/live/'+state.live.id,{method:'POST',body:JSON.stringify({intervention:{action,space_ids:[state.selected.slice(5)]}})});
    state.run.settings=response.settings;appendFrames([response.frame]);state.time=response.frame.time_s;appliedTime=-1;render();
    $('job-status').textContent=`${action} applied at ${response.event.time_s} simulated seconds. The action is recorded in the download.`;
  }catch(error){$('job-status').textContent=error.message;}finally{if(wasPlaying)setPlaying(true);}
}
async function submit(event) {
  if(window.PandaEnvironments.isPending()){event.preventDefault();return;}
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
  state.scene=await api('/api/scene');
  await window.PandaEnvironments.init(state.scene,{apply:applyEnvironment,current:()=>currentEnvironment,context:reloadEnvironmentContext,validate:payload=>window.PandaPlatform.environmentRequest(payload)});
  currentEnvironment=window.PandaEnvironments.walmart();createScene();window.PandaPlatform.attachViewer(viewer);updatePolicyOptions();loadContext().catch(error=>{$('map-status').textContent=error.message;});
  $('scenario').addEventListener('submit',submit);
  $('supply-mode').addEventListener('change',()=>{if($('supply-mode').value==='pick')beginOccupancyDraft();else{endOccupancyDraft();updateSupplyControls();render();}});
  $('map-action').addEventListener('change',()=>{if($('map-action').value==='occupied'&&!state.editingOccupancy)beginOccupancyDraft();});
  $('free-count').addEventListener('input',updateSupplyControls);
  updateSupplyControls();
  $('driver-select').addEventListener('change',()=>{bringMapIntoView();state.selected=$('driver-select').value?'driver:'+$('driver-select').value:null;inspect();if(state.run&&!state.editingOccupancy){render();updateTraffic();}});
  $('clear-selection').addEventListener('click',()=>{draft.occupied.clear();draft.closed.clear();updateDraft();});
  $('clear-schedule').addEventListener('click',()=>{draft.schedule=[];updateDraft();});
  $('schedule-intervention').addEventListener('click',()=>{if(!state.selected?.startsWith('slot:')){$('job-status').textContent='Inspect a usable space first.';return;}if(!$('intervention-time').reportValidity())return;draft.schedule.push({time_s:Number($('intervention-time').value),action:$('intervention-action').value,space_ids:[state.selected.slice(5)]});updateDraft();});
  for(const button of document.querySelectorAll('[data-intervention]'))button.addEventListener('click',()=>intervene(button.dataset.intervention));
  for(const id of ['show-trajectory','show-congestion','follow-driver','show-pedestrians'])$(id).addEventListener('change',()=>{if(state.run&&!state.editingOccupancy){render();updateTraffic();}});
  $('info-buttons').addEventListener('click',event=>{const button=event.target.closest('[data-mode]');if(!button)return;
    $('information').value=button.dataset.mode;$('info-help').textContent=infoText[button.dataset.mode];
    document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('selected',b===button));});
  $('occupancy').addEventListener('input',updateSupplyControls);
  $('follow-driver').addEventListener('change',bringMapIntoView);
  $('download-congestion').addEventListener('click',downloadCongestion);
  $('congestion-episodes').addEventListener('click',event=>{const button=event.target.closest('[data-traffic-segment]');if(button)focusTrafficSegment(button.dataset.trafficSegment);});
  $('play').addEventListener('click',togglePlayback);
  $('pause-live').addEventListener('click',togglePlayback);
  $('simulation-duration').addEventListener('change',()=>{const custom=$('simulation-duration').value==='custom';$('custom-duration-container').hidden=!custom;$('custom-duration-value').disabled=!custom;});
  $('custom-duration-unit').addEventListener('change',()=>{const input=$('custom-duration-value'),seconds=Number(input.value)*(Number($('custom-duration-unit').value)===1?60:1/60);updateDurationLimits();input.value=Number(seconds.toFixed(2));});updateDurationLimits();
  $('timeline').addEventListener('input',()=>{state.time=Number($('timeline').value);render();});
  $('reset-camera').addEventListener('click',()=>home());
  $('overhead-camera').addEventListener('click',()=>home(true));
  $('live-button').addEventListener('click',startLive);
  $('history').addEventListener('change',()=>loadRun($('history').value).catch(error=>{$('job-status').textContent=error.message;}));
  $('show-context').addEventListener('change',()=>state.context.forEach(m=>{m.show=$('show-context').checked;}));
  $('show-module-labels').addEventListener('change',()=>{for(const e of state.moduleLabels??[])e.show=$('show-module-labels').checked;});
  $('module-list').addEventListener('click',event=>{const button=event.target.closest('[data-module]');if(button)focusParkingModule(button.dataset.module);});
  $('show-network').addEventListener('change',()=>state.networks.forEach(e=>{e.show=$('show-network').checked;}));
  $('download').addEventListener('click',async()=>{if(!state.run)return;const url=URL.createObjectURL(new Blob([JSON.stringify(state.run)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`panda-${state.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  await loadRun('baseline');requestAnimationFrame(tick);
  // Default planning layout; the saved reference run (original layout) stays under Saved runs.
  if(window.PandaEnvironments.get('walmart_corrected'))await window.PandaEnvironments.activate('walmart_corrected');
}
init().catch(error=>{$('map-status').textContent=error.message;$('job-status').textContent=error.message;console.error(error);});
