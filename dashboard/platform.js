/* Public website orchestration. Parking decisions remain in the Python ABM. */
(() => {
  const el=id=>document.getElementById(id), names={deterministic:'Deterministic',rum:'Stochastic',cpt:'CPT'}, infos={unaided:'Unaided',aisle:'Aisle information',space:'Space information'};
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
  const jobs=new Map(), replays=new Map();let engine, comparison, measurement, busy=false, runtimeLoad, renderedFrames=0, study;
  const metricNames={search_s:'Search (s)',success_pct:'Parking success (%)',walk_m:'Walk (m)',exit_m:'Exit proximity (m)',failed_claims:'Failed claims / driver',joint_search_walk_s:'Combined time (s)'};
  function download(value,name,type='application/json'){
    name=name.replace(/(\.[^.]+)$/,`-${Date.now()}$1`);
    const href=URL.createObjectURL(new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}));
    const a=document.createElement('a');a.href=href;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
  }
  async function json(url){const r=await fetch(url);if(!r.ok)throw Error(`Could not load ${url} (${r.status})`);return r.json();}
  function getEngine(){
    return engine??=new PandaEngine(event=>{
      if(event.type==='ready'){runtimeLoad=event;el('engine-status').textContent=`Python ${event.runtime.python} · ready`;} 
      else if(event.type==='progress'||event.type==='error')el('engine-status').textContent=event.message;
      else if(event.type==='comparison-progress'){
        el('comparison-progress').max=event.total;el('comparison-progress').value=event.done;
        el('comparison-status').textContent=`Completed ${event.done} / ${event.total} simulations · ${names[event.model]} · ${infos[event.information]} · seed ${event.seed}`;
      }
    });
  }
  function setBusy(value){busy=value;for(const id of ['compare-start','benchmark-start','run-button','live-button'])if(el(id))el(id).disabled=value;el('cancel-compute').disabled=!value;}
  async function pauseLive(){if(window.setPlaying)window.setPlaying(false);if(window.closeLive)await window.closeLive();}
  function showPage(page){
    document.body.dataset.page=page;
    document.querySelector('.workspace').hidden=page!=='simulate';
    for(const [name,id] of [['compare','comparison-view'],['study','study-view'],['about','about-view']])el(id).hidden=name!==page;
    for(const button of document.querySelectorAll('[data-page]')){if(button.dataset.page===page)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');}
    if(page!=='simulate'&&window.setPlaying)window.setPlaying(false);
    if(page==='simulate')window.dispatchEvent(new Event('resize'));
  }
  function table(rows,effect=false){
    const keys=effect?['search_s','success_pct','walk_m','exit_m','failed_claims','joint_search_walk_s']:['search_s','success_pct','walk_m','exit_m','failed_claims'];
    return `<div class="table-scroll"><table class="results-table"><thead><tr><th>Model / information</th>${keys.map(k=>`<th>${effect&&k==='success_pct'?'Success change (pp)':metricNames[k]}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr><td><b>${names[r.model]}</b><br><span class="condition-tag condition-${r.information}"></span>${infos[r.information]}</td>${keys.map(k=>{const v=r.metrics[k];return `<td>${number(v.mean)}${v.low==null?'<small>No interval</small>':`<small>[${number(v.low)}, ${number(v.high)}]</small>`}${v.replications===0?'<small>No eligible observations</small>':''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;
  }
  function bars(rows,key,label){
    const max=Math.max(...rows.map(r=>Number(r.metrics[key].mean)||0),1);
    return `<article class="panel"><h2>${label}</h2><div class="metric-bars">${rows.map(r=>`<div class="bar-row"><span>${names[r.model]} · ${infos[r.information].replace(' information','')}</span><div class="bar-track"><div class="bar-fill condition-${r.information}" style="width:${Math.max(0,(r.metrics[key].mean??0)/max*100)}%"></div></div><b>${number(r.metrics[key].mean,1)}</b></div>`).join('')}</div></article>`;
  }
  function displayComparison(result){
    el('comparison-results').innerHTML=`<div class="comparison-outcomes">${bars(result.cells,'search_s','Mean search duration')}${bars(result.cells,'success_pct','Parking success')}</div><article class="panel"><h2>Outcomes by information condition</h2>${table(result.cells)}</article><article class="panel"><h2>Change from unaided search</h2>${table(result.effects,true)}<p class="help">Pointwise 95% percentile bootstrap intervals use 10,000 resamples of whole matched replications. No interval is calculated from a single replication. Intervals are not adjusted for multiple comparisons. Walking changes can reflect different parked populations; combined time uses drivers parked in both conditions.</p></article>`;
    el('comparison-status').textContent=`Completed ${result.runs.length} full-lifecycle simulations in ${number(result.wall_s,1)} s. Population and initial occupancy matched across all conditions. ${result.replications} replication${result.replications===1?'':'s'} per condition.`;
    el('comparison-json').disabled=false;el('comparison-csv').disabled=false;
    const details=document.createElement('details');details.className='panel';details.innerHTML='<summary>Reproducibility record</summary><pre id="comparison-provenance"></pre>';el('comparison-results').append(details);
    verifyReference(result).then(record=>{el('comparison-provenance').textContent=JSON.stringify(record,null,2);}).catch(error=>{el('comparison-provenance').textContent=JSON.stringify({reference_check_error:error.message});});
  }
  async function verifyReference(result){
    const record={source_bundle_sha256:result.source_manifest?.bundle_sha256??null,runtime:result.runtime,matched_inputs_within_each_seed:true};
    const s=result.settings;
    if(s.seed!==1000||s.population_size!==80||s.occupancy!==.8||s.arrival_interval_s!==20||result.replications!==1){record.reference_check='Available for seed 1000, 80 drivers, 80% occupancy, 20-second arrivals and one replication.';return record;}
    const ref=await json('engine/full-size-fixture.json');let maxInput=0,maxOutcome=0,count=0;const errors=[];
    if(!record.source_bundle_sha256)errors.push('Verified source manifest missing');
    function walk(a,b,path){
      if(a&&b&&typeof a==='object'&&typeof b==='object'){
        const keys=Object.keys(a);if(keys.length!==Object.keys(b).length){errors.push(path+' length');return;}
        for(const key of keys){if(!(key in b)){errors.push(path+'.'+key);continue;}walk(a[key],b[key],path+'.'+key);}
      }else if(typeof a==='number'&&typeof b==='number'){maxInput=Math.max(maxInput,Math.abs(a-b));if(Math.abs(a-b)>1e-12)errors.push(path);}
      else if(a!==b)errors.push(path);
    }
    if(!result.populations?.['1000'])errors.push('Population export missing');else walk(result.populations['1000'],ref.population,'population');
    let rawHashesMatch=true;
    for(const run of result.runs){const expected=ref.runs.find(r=>r.model===run.settings.model&&r.information===run.settings.information);if(!expected){errors.push('Reference arm missing');continue;}
      rawHashesMatch&&=run.population_sha256===expected.population_sha256;
      if(run.outcomes.length!==expected.outcomes.length)errors.push('Driver count');
      if(run.initial_occupancy_sha256!==expected.initial_occupancy_sha256)errors.push('Initial occupancy');
      const byId=new Map(expected.outcomes.map(o=>[o.driver,o]));
      for(const actual of run.outcomes){count++;const wanted=byId.get(actual.driver);if(!wanted){errors.push('Unknown driver');continue;}
        for(const key of Object.keys(wanted)){const a=actual[key],b=wanted[key];if(typeof a==='number'&&typeof b==='number'){maxOutcome=Math.max(maxOutcome,Math.abs(a-b));if(Math.abs(a-b)>1e-8)errors.push(actual.driver+'.'+key);}else if(a!==b)errors.push(actual.driver+'.'+key);}
      }
    }
    return {...record,passed:errors.length===0,scenarios:result.runs.length,driver_scenario_records:count,archive:'tcss_first_batch_20261028',population:80,occupancy:.8,seed:1000,models:result.models,absolute_tolerance:1e-8,population_numeric_tolerance:1e-12,max_absolute_population_difference:maxInput,max_absolute_outcome_difference:maxOutcome,raw_population_hashes_match:rawHashesMatch,reference_csv_sha256:ref.source_csv_sha256,errors};
  }
  async function startComparison(){
    if(busy||!el('scenario').reportValidity()||!el('replications').reportValidity())return;
    const models=[...document.querySelectorAll('[name=compare-model]:checked')].map(x=>x.value);
    if(!models.length){el('comparison-status').textContent='Select at least one decision model.';return;}
    setBusy(true);comparison=null;el('comparison-results').innerHTML='';el('comparison-json').disabled=true;el('comparison-csv').disabled=true;el('comparison-progress').hidden=false;el('comparison-progress').value=0;
    try{
      await pauseLive();el('comparison-status').textContent='Preparing the Python engine…';
      comparison=await getEngine().request('compare',{settings:window.settingsFromForm(),models,replications:Number(el('replications').value)});
      comparison.source_manifest=runtimeLoad.manifest;displayComparison(comparison);
    }catch(error){el('comparison-status').textContent=error.message;}
    finally{setBusy(false);}
  }
  function comparisonCSV(){
    const rows=[['type','model','information','metric','mean','ci_low','ci_high','replications']];
    for(const [type,values] of [['outcome',comparison.cells],['informed_minus_unaided',comparison.effects]])for(const row of values)for(const [metric,value] of Object.entries(row.metrics))rows.push([type,row.model,row.information,metric,value.mean,value.low,value.high,value.replications]);
    download(rows.map(r=>r.map(v=>v??'').join(',')).join('\n'),'panda-matched-comparison.csv','text/csv');
  }
  function renderStudy(){
    const occupancy=Number(el('study-occupancy').value);
    const cells=study.cells.filter(r=>r.variant==='base'&&Number(r.occupancy)===occupancy).map(r=>({model:r.model,information:r.information,metrics:Object.fromEntries(Object.entries({search_s:r.mean_search_s,success_pct:100*Number(r.success),walk_m:r.mean_walk_parked_m,exit_m:r.mean_exit_parked_m,failed_claims:r.claims_per_arrival}).map(([k,v])=>[k,{mean:Number(v)}]))}));
    const effects=study.effects.filter(r=>r.variant==='base'&&Number(r.occupancy)===occupancy);
    el('study-results').innerHTML=`<div class="comparison-outcomes">${bars(cells,'search_s','Mean search duration')}${bars(cells,'success_pct','Parking success')}</div>${table(cells)}<h2>Paired information effects</h2><div class="table-scroll"><table class="results-table"><thead><tr><th>Model</th><th>Information</th><th>Metric</th><th>Change</th><th>95% interval</th></tr></thead><tbody>${effects.filter(r=>['mean_search_s','success','mean_walk_parked_m','mean_exit_parked_m','claims_per_arrival'].includes(r.metric)).map(r=>{const scale=r.metric==='success'?100:1;return `<tr><td>${names[r.model]??escape(r.model)}</td><td>${infos[r.information]}</td><td>${{mean_search_s:'Search (s)',success:'Success (pp)',mean_walk_parked_m:'Walk (m)',mean_exit_parked_m:'Exit proximity (m)',claims_per_arrival:'Failed claims / driver'}[r.metric]}</td><td>${number(Number(r.delta)*scale)}</td><td>[${number(Number(r.ci_low)*scale)}, ${number(Number(r.ci_high)*scale)}]</td></tr>`;}).join('')}</tbody></table></div><p class="help">30 matched replications per condition. Pointwise bootstrap intervals; no multiplicity adjustment. Distances include parked drivers only. These are simulated study results, not measurements from the physical facility.</p>`;
  }
  function compareOutcomes(expected,actual){
    const errors=[];if(expected.outcomes.length!==actual.outcomes.length)errors.push('Driver count differs');
    if(expected.initial_occupancy_sha256!==actual.initial_occupancy_sha256)errors.push('Initial occupancy differs');
    const expectedById=new Map(expected.outcomes.map(o=>[o.driver,o]));
    for(const got of actual.outcomes){const want=expectedById.get(got.driver);if(!want){errors.push(`Unknown driver ${got.driver}`);continue;}
      for(const key of ['success','chosen_space','search_s','search_distance_m','walk_m','exit_distance_m','lost_claims','parking_time_s']){
        const a=want[key],b=got[key];if(typeof a==='number'&&typeof b==='number'){if(Math.abs(a-b)>1e-8)errors.push(`${got.driver}.${key}: ${a} vs ${b}`);}else if(a!==b)errors.push(`${got.driver}.${key} differs`);
      }
    }return errors;
  }
  async function benchmark(){
    if(busy)return;setBusy(true);
    const monitor=document.createElement('div');monitor.className='benchmark-monitor';monitor.setAttribute('role','status');
    const monitorText=document.createElement('span'),stop=document.createElement('button');stop.className='light-button';stop.textContent='Stop performance test';stop.addEventListener('click',()=>getEngine().cancel());monitor.append(monitorText,stop);document.body.append(monitor);
    const status=text=>{monitorText.textContent=text;el('benchmark-status').textContent=text;};
    measurement={schema_version:1,started_utc:new Date().toISOString(),user_agent:navigator.userAgent,logical_processors:navigator.hardwareConcurrency??null,device_memory_gb:navigator.deviceMemory??null,viewport:{width:innerWidth,height:innerHeight,device_pixel_ratio:devicePixelRatio},cache_state:'Uncontrolled browser cache; initialization is not a cold-start estimate',fixtures:[],timings:[],rendering_scope:'Fixed stationary 3D reference scene (80-driver replay paused at time zero) while the worker simulates 20, 80 or 120 drivers; this does not measure animated traffic',tolerance_absolute:1e-8};
    try{
      await pauseLive();showPage('simulate');
      if(!window.loadRun)throw Error('The Cesium scene must load before the rendering test.');
      await window.loadRun('baseline');
      const fixtures=await json('engine/native-fixtures.json');measurement.native_runtime=fixtures.runtime;
      status('Loading Python and checking native/browser outcomes…');measurement.browser_runtime=await getEngine().request('ready');measurement.initialization={runtime:runtimeLoad.runtime,initialize_ms:runtimeLoad.initialize_ms};
      measurement.source_manifest=runtimeLoad.manifest;
      for(let i=0;i<fixtures.cases.length;i++){
        const expected=fixtures.cases[i];status(`Verification ${i+1} / ${fixtures.cases.length} · ${names[expected.settings.model]} · ${expected.settings.information}`);
        const actual=await getEngine().request('summary',expected.settings), errors=compareOutcomes(expected,actual);
        measurement.fixtures.push({settings:expected.settings,passed:errors.length===0,errors,population_hash_exact:expected.population_sha256===actual.population_sha256});
      }
      if(measurement.fixtures.some(r=>!r.passed))throw Error('Native/browser outcome verification failed. Download the measurements for details.');
      for(const n of [20,80,120])for(let repeat=0;repeat<3;repeat++){
        status(`Performance · ${n} drivers · repetition ${repeat+1} / 3. Keep this tab visible.`);
        const intervals=[];let previous=null,active=true,visible=true;
        const sample=t=>{if(!active)return;if(previous!==null)intervals.push(t-previous);previous=t;if(document.hidden)visible=false;requestAnimationFrame(sample);};requestAnimationFrame(sample);
        const beforeFrames=renderedFrames,start=performance.now();
        const result=await getEngine().request('summary',{model:'cpt',information:'space',population_size:n,occupancy:.8,seed:7000+repeat,arrival_interval_s:20});
        const request_ms=performance.now()-start;active=false;
        const sorted=intervals.slice().sort((a,b)=>a-b),q=p=>sorted.length?sorted[Math.floor((sorted.length-1)*p)]:null;
        measurement.timings.push({population:n,repeat,request_ms,python_wall_s:result.wall_s,python_initialize_s:result.initialize_wall_s,simulated_duration_s:result.simulated_duration_s,rendered_frames:renderedFrames-beforeFrames,raf_samples:intervals.length,raf_median_ms:q(.5),raf_p95_ms:q(.95),visible_during_measurement:visible});
      }
      measurement.status='passed';measurement.finished_utc=new Date().toISOString();
      status(`Verified ${measurement.fixtures.length} native/browser fixtures. Completed ${measurement.timings.length} performance measurements.`);
    }catch(error){measurement.status='failed';measurement.error=error.message;}
    finally{el('benchmark-status').textContent=JSON.stringify(measurement,null,2);el('benchmark-download').disabled=false;monitor.remove();setBusy(false);showPage('about');}
  }
  window.PandaPlatform={
    attachViewer(viewer){
      viewer.scene.postRender.addEventListener(()=>{renderedFrames++;});
      const button=document.createElement('button');button.className='light-button';button.textContent='Export 3D view';document.querySelector('.view-buttons').append(button);
      button.addEventListener('click',()=>{const remove=viewer.scene.postRender.addEventListener(()=>{remove();try{const source=viewer.scene.canvas,exportCanvas=document.createElement('canvas');exportCanvas.width=source.width;exportCanvas.height=source.height+30;const context=exportCanvas.getContext('2d');context.fillStyle='#f5f8f5';context.fillRect(0,0,exportCanvas.width,exportCanvas.height);context.drawImage(source,0,0);context.fillStyle='#243f3b';context.font='12px sans-serif';context.fillText('Map data (c) OpenStreetMap contributors | CesiumJS | PANDA: estimated geometry',10,source.height+20);exportCanvas.toBlob(blob=>{if(!blob)return;const href=URL.createObjectURL(blob),a=document.createElement('a');a.href=href;a.download='panda-3d-view-'+Date.now()+'.png';a.click();setTimeout(()=>URL.revokeObjectURL(href),1000);});}catch(error){el('job-status').textContent=error.message;}});viewer.scene.requestRender();});
    },
    async api(url,options={}){
      const payload=options.body?JSON.parse(options.body):{};
      if(url==='/api/scene')return json('scene.json');
      if(url==='/api/runs'&&!options.method)return [{id:'baseline',status:'complete',settings:{model:'cpt',information:'unaided',occupancy:.4,population_size:80,seed:1000}},...jobs.values()];
      if(url==='/api/runs'&&options.method==='POST'){
        if(busy)throw Error('Another computation is in progress.');setBusy(true);const id=crypto.randomUUID().replaceAll('-','');
        const job={id,status:'running',settings:payload};jobs.set(id,job);
        getEngine().request('record',payload).then(data=>{replays.set(id,data);job.status='complete';job.summary=data.summary;
          while(replays.size>4){const oldest=replays.keys().next().value;replays.delete(oldest);jobs.delete(oldest);}
        }).catch(e=>{job.status='failed';job.error=e.message;}).finally(()=>setBusy(false));return job;
      }
      if(url.startsWith('/api/runs/')){const [,id,suffix]=url.match(/^\/api\/runs\/([^/]+)(?:\/(data))?$/)??[];
        if(suffix){if(id==='baseline')return json('reference.json');if(replays.has(id))return replays.get(id);throw Error('This replay is no longer in memory. Compute it again or use your downloaded copy.');}
        if(jobs.has(id))return jobs.get(id);throw Error('Unknown simulation');
      }
      if(url==='/api/live'){if(busy)throw Error('Another computation is in progress.');return {id:'browser-live',...await getEngine().request('live',payload)};}
      if(url.startsWith('/api/live/'))return getEngine().request(payload.action==='close'?'close':'advance',payload);
      throw Error('Unknown platform operation');
    }
  };
  async function initializeUI(){
    const r=await fetch('platform-views.html');if(!r.ok)throw Error('Platform views could not be loaded');document.querySelector('main').insertAdjacentHTML('beforeend',await r.text());
    document.querySelector('.platform-nav').addEventListener('click',event=>{const button=event.target.closest('[data-page]');if(button)showPage(button.dataset.page);});
    el('compare-start').addEventListener('click',startComparison);el('cancel-compute').addEventListener('click',()=>{if(engine)engine.cancel();});
    el('comparison-json').addEventListener('click',()=>download(comparison,'panda-matched-comparison.json'));el('comparison-csv').addEventListener('click',comparisonCSV);
    el('benchmark-start').addEventListener('click',benchmark);el('benchmark-download').addEventListener('click',()=>download(measurement,'panda-platform-performance.json'));
    el('study-occupancy').addEventListener('change',renderStudy);study=await json('study-results.json');renderStudy();showPage('simulate');
  }
  document.addEventListener('DOMContentLoaded',()=>initializeUI().catch(error=>{el('engine-status').textContent=error.message;console.error(error);}));
})();
