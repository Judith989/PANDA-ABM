/* Local environment library. Models are never uploaded to a server. */
(()=>{
  const el=id=>document.getElementById(id),library=new Map();let hooks,pending,previous,loading=false;
  const sha=async bytes=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
  function save(value,name){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function inspectGLB(file){
    if(!file.name.toLowerCase().endsWith('.glb')||file.size>100*1024*1024)throw Error('Use self-contained GLB files, at most 100 MB each.');
    const bytes=await file.arrayBuffer(),v=new DataView(bytes);
    if(bytes.byteLength<20||v.getUint32(0,true)!==0x46546c67||v.getUint32(4,true)!==2||v.getUint32(8,true)!==bytes.byteLength)throw Error(file.name+': invalid GLB 2.0 header.');
    const size=v.getUint32(12,true);if(v.getUint32(16,true)!==0x4e4f534a||20+size>bytes.byteLength)throw Error('GLB JSON chunk is missing.');
    const data=JSON.parse(new TextDecoder().decode(new Uint8Array(bytes,20,size)).replace(/\0+$/,''));
    if(!data.meshes?.length)throw Error(file.name+': no meshes found.');
    for(const item of [...(data.buffers??[]),...(data.images??[])])if(item.uri&&!item.uri.startsWith('data:'))throw Error('External model resources are unsupported. Export a self-contained GLB.');
    return {file,descriptor:{name:file.name,sha256:await sha(bytes)}};
  }
  function alignmentFromForm(){const a={};for(const k of ['east_m','north_m','height_m','scale'])a[k]=Number(el('env-'+k).value);a.rotation_radians=Number(el('env-rotation').value)*Math.PI/180;a.up_axis=el('env-up').value;a.forward_axis=el('env-forward').value;return a;}
  function showAlignment(a){for(const k of ['east_m','north_m','height_m','scale'])el('env-'+k).value=a[k];el('env-rotation').value=a.rotation_radians*180/Math.PI;el('env-up').value=a.up_axis??'Y';el('env-forward').value=a.forward_axis??'X';}
  function simulationLock(value){const review=!!hooks?.current?.()?.environment?.config?.meta?.review_required;for(const id of ['live-button','run-button','compare-start','benchmark-start','environment-select'])if(el(id))el(id).disabled=value||(review&&id!=='environment-select');}
  async function display(item){await hooks.apply(item);el('environment-select').value=item.key;}
  function status(message){el('environment-status').textContent=message;}
  function add(item){library.set(item.key,item);const existing=[...el('environment-select').options].find(o=>o.value===item.key);if(existing)existing.text=item.name;else el('environment-select').add(new Option(item.name,item.key));}
  // User-chosen names: the environment name becomes meta.lot_name (kept in the
  // downloaded configuration); model names travel as model_files[].label.
  let importedLabels={};
  async function prefillNames(){
    const file=el('environment-json').files[0];importedLabels={};
    if(!file||file.size>8_000_000)return;
    try{const parsed=JSON.parse(await file.text()),config=parsed.config??parsed;
      if(!el('env-name').value.trim()||el('env-name').dataset.auto==='1'){el('env-name').value=parsed.name??config.meta?.lot_name??'';el('env-name').dataset.auto='1';}
      for(const m of parsed.model_files??[])if(m.label)importedLabels[m.name]=m.label;renderModelNames();}catch{}
  }
  function renderModelNames(){
    const files=[...el('environment-models').files],previous=Object.fromEntries([...document.querySelectorAll('[data-model-file]')].map(i=>[i.dataset.modelFile,i.value]));
    el('env-model-names').innerHTML='';
    for(const [i,f] of files.entries()){
      const label=document.createElement('label'),input=document.createElement('input');
      label.htmlFor='env-model-name-'+i;label.textContent='Name for '+f.name;
      input.id='env-model-name-'+i;input.type='text';input.maxLength=80;input.dataset.modelFile=f.name;input.autocomplete='off';
      input.value=previous[f.name]??importedLabels[f.name]??f.name.replace(/\.glb$/i,'').replace(/[_-]+/g,' ');
      el('env-model-names').append(label,input);
    }
  }
  function modelLabel(name){return document.querySelector(`[data-model-file="${CSS.escape(name)}"]`)?.value.trim()||name;}
  async function importPreview(){
    if(loading||pending)return;loading=true;simulationLock(true);let blobs=[];
    try{
      const file=el('environment-json').files[0];if(!file||file.size>8_000_000)throw Error('Choose a lot or environment JSON file smaller than 8 MB.');
      const parsed=JSON.parse(await file.text()),files=[...el('environment-models').files];if(files.length>8||files.reduce((n,f)=>n+f.size,0)>200*1024*1024)throw Error('Use at most eight models, 200 MB total.');
      const checked=[];for(const f of files)checked.push(await inspectGLB(f));
      if(new Set(files.map(f=>f.name)).size!==files.length)throw Error('Model filenames must be distinct.');
      if(parsed.model_files?.length){for(const expected of parsed.model_files){if(!checked.some(c=>c.descriptor.name===expected.name&&c.descriptor.sha256===expected.sha256))throw Error('Select the original model matching '+expected.name+'.');}}
      const chosen=el('env-name').value.trim();if(chosen.length>80)throw Error('Use an environment name of at most 80 characters.');
      const config=parsed.config??parsed,named=chosen?{...config,meta:{...config.meta,lot_name:chosen}}:config;
      const payload={...parsed,config:named,id:'custom-'+crypto.randomUUID(),model_files:checked.map(c=>({...c.descriptor,label:modelLabel(c.descriptor.name)}))};
      delete payload.name;
      status('Checking coordinates, restrictions and aisle connectivity…');const env=await hooks.validate(payload);
      previous=hooks.current();blobs=checked.map(c=>({name:c.file.name,label:modelLabel(c.file.name),url:URL.createObjectURL(c.file)}));
      pending={key:env.id,name:env.name,environment:env,models:blobs,scene:{config:env.config,alignment:env.alignment}};
      el('environment-select').add(new Option('Preview · '+env.name,env.id));
      showAlignment(env.alignment);el('alignment-preview').hidden=false;el('confirm-environment').disabled=true;el('alignment-confirmed').checked=false;el('alignment-confirmed').disabled=false;
      await hooks.apply(pending);status(`“${env.name}”: ${env.validation.spaces} spaces, ${env.validation.usable_spaces} usable. Network connected.${blobs.length?' Models: '+blobs.map(b=>b.label).join(', ')+'.':''} Adjust the model, inspect spaces and aisles, then confirm. ${env.validation.warnings.join(' ')}`);
    }catch(error){for(const b of blobs)URL.revokeObjectURL(b.url);if(pending)for(const option of [...el('environment-select').options])if(option.value===pending.key)option.remove();pending=null;el('alignment-preview').hidden=true;if(previous)await display(previous);status(error.message);simulationLock(false);}
    finally{loading=false;if(!pending)simulationLock(false);else {el('environment-select').disabled=true;el('confirm-environment').disabled=!el('alignment-confirmed').checked;}}
  }
  async function updatePreview(){
    if(!pending||loading)return;loading=true;el('confirm-environment').disabled=true;el('alignment-confirmed').checked=false;el('alignment-confirmed').disabled=true;
    const fields=['env-east_m','env-north_m','env-height_m','env-scale','env-rotation','env-up','env-forward'];for(const id of fields)el(id).disabled=true;
    try{const next=await hooks.validate({...pending.environment,alignment:alignmentFromForm()});pending.environment=next;pending.scene.alignment=next.alignment;await hooks.context(pending);el('alignment-confirmed').disabled=false;status('Alignment updated. Check the 3D model against spaces, doors and aisles before confirming.');}
    catch(e){status(e.message);}
    finally{loading=false;for(const id of fields)el(id).disabled=false;}
  }
  const MESSAGES={
    downtown_laramie:'Downtown loaded: 241 configured bay estimates, eight destinations and 3D buildings. Off-street inventory is incomplete; see the numbered geometry audit. Choose your scenario and start a live simulation. Geometry and traffic settings are experimental assumptions.',
    walmart_satellite:'Satellite estimate: 472 provisional records; 396 usable and 7 accessible designations under inherited-rule assumptions. Not field verified. It traces only one row of each double row; the corrected layout adds the other.',
    walmart_corrected:'Corrected from imagery: angled double rows traced from satellite imagery (909 bays, 790 usable) with regenerated aisles and walking paths. Not surveyed. The published study results use the original 1,315-record estimate, still available in this list and under Saved runs.'};
  async function activate(key){
    if(loading||!library.has(key))return;loading=true;simulationLock(true);el('environment-select').value=key;
    try{await display(library.get(key));status(MESSAGES[key]??'Environment loaded. Supply selections were reset. Saved study results use the original Walmart estimate.');}
    catch(e){status(e.message);}finally{loading=false;simulationLock(false);}
  }
  window.PandaEnvironments={
    activate,
    async init(scene,callbacks){hooks=callbacks;add({key:'walmart',name:'Walmart · original estimate (1,315)',environment:null,scene,models:[{name:'parking_asphalt.glb',url:'assets/parking_asphalt.glb'},{name:'walmart_building.glb',url:'assets/walmart_building.glb'}]});
      const response=await fetch('environments.json');if(!response.ok)throw Error('Environment catalog could not load');const catalog=await response.json();add({key:'synthetic',name:'Synthetic transfer · fictional layout',environment:catalog.synthetic,scene:{config:catalog.synthetic.config,alignment:catalog.synthetic.alignment},models:[{name:'synthetic_pavement.glb',url:'assets/synthetic_pavement.glb'}]});
      add({key:'walmart_satellite',name:'Walmart · satellite estimate (472)',environment:catalog.satellite,scene:{config:catalog.satellite.config,alignment:catalog.satellite.alignment},models:[{name:'parking_asphalt.glb',url:'assets/parking_asphalt.glb'},{name:'walmart_building.glb',url:'assets/walmart_building.glb'}]});
      if(catalog.corrected)add({key:'walmart_corrected',name:'Walmart · corrected from imagery ('+catalog.corrected.validation.spaces+')',environment:catalog.corrected,scene:{config:catalog.corrected.config,alignment:catalog.corrected.alignment},models:[{name:'parking_asphalt.glb',url:'assets/parking_asphalt.glb'},{name:'walmart_building.glb',url:'assets/walmart_building.glb'}]});
      // The default planning layout is listed first.
      const corrected=[...el('environment-select').options].find(o=>o.value==='walmart_corrected');if(corrected)el('environment-select').prepend(corrected);
      if(catalog.downtown)add({key:'downtown_laramie',name:'Downtown Laramie · streets and parking',environment:catalog.downtown,scene:{config:catalog.downtown.config,alignment:catalog.downtown.alignment},models:[{name:'downtown_buildings.glb',url:'assets/downtown_buildings.glb'}]});
      el('environment-select').addEventListener('change',()=>activate(el('environment-select').value));
      el('preview-environment').addEventListener('click',importPreview);
      el('environment-json').addEventListener('change',prefillNames);el('environment-models').addEventListener('change',renderModelNames);
      el('env-name').addEventListener('input',()=>{el('env-name').dataset.auto='0';});
      el('update-alignment').addEventListener('click',updatePreview);
      for(const id of ['env-east_m','env-north_m','env-height_m','env-scale','env-rotation','env-up','env-forward'])el(id).addEventListener('input',()=>{el('alignment-confirmed').checked=false;el('alignment-confirmed').disabled=true;el('confirm-environment').disabled=true;status('Apply alignment preview before confirming the changed transform.');});
      el('alignment-confirmed').addEventListener('change',()=>{el('confirm-environment').disabled=loading||!el('alignment-confirmed').checked;});
      el('confirm-environment').addEventListener('click',()=>{if(loading||!pending||!el('alignment-confirmed').checked)return;add(pending);el('environment-select').value=pending.key;pending=null;previous=null;el('alignment-preview').hidden=true;simulationLock(false);status(`“${library.get(el('environment-select').value)?.name}” is ready. Files remain in this tab. Download its configuration and keep the original GLBs to reload it later.`);});
      el('cancel-environment').addEventListener('click',async()=>{if(loading||!pending)return;const discard=pending;for(const option of [...el('environment-select').options])if(option.value===discard.key)option.remove();pending=null;el('alignment-preview').hidden=true;await display(previous);previous=null;for(const b of discard.models)URL.revokeObjectURL(b.url);simulationLock(false);status('Import cancelled. Previous environment restored.');});
      el('export-environment').addEventListener('click',async()=>{try{const item=hooks.current(),value=item.environment??catalog.walmart;save(value,`panda-environment-${String(item.name??'walmart').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'')||'custom'}.json`);}catch(e){status(e.message);}});
      el('environment-template').addEventListener('click',()=>save(catalog.template,'panda-lot-template.json'));
    },
    walmart(){return library.get('walmart');},
    get(key){return library.get(key);},
    select(key){el('environment-select').value=key;},
    isPending(){return !!pending;},
    async forRun(env){if(!env)return library.get('walmart');const exact=library.get(env.id);if(exact?.environment?.environment_sha256===env.environment_sha256)return exact;for(const item of library.values())if(item.environment?.environment_sha256===env.environment_sha256)return item;
      return {key:env.id,name:env.name,environment:env,scene:{config:env.config,alignment:null},models:[]};}
  };
})();
