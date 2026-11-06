/* Local developer check, intentionally excluded from the public build. */
let report;
document.getElementById('start').onclick=async()=>{
  const status=document.getElementById('status');document.getElementById('start').disabled=true;
  try{
    const fixtures=await (await fetch('engine/traffic-fixtures.json')).json();
    let manifest;
    const engine=new PandaEngine(e=>{if(e.type==='progress')status.textContent=e.message;if(e.type==='ready')manifest=e.manifest;});
    await engine.request('ready');
    for(const [name,hash] of Object.entries(fixtures.source_sha256))if(manifest.source_sha256[name]!==hash)throw Error('Stale fixture or bundle: '+name);
    const checks=[];
    for(const fixture of fixtures.cases){
      status.textContent=`Checking ${fixture.settings.model}, ${fixture.settings.initial_free_count} empty spaces…`;
      const result=await engine.request('summary',fixture.settings);let maxError=0;const errors=[];
      function compare(a,b,path){
        if(typeof a==='number'&&typeof b==='number'){maxError=Math.max(maxError,Math.abs(a-b));if(Math.abs(a-b)>1e-8)errors.push(path);}
        else if(a&&typeof a==='object'&&b&&typeof b==='object'){if(Array.isArray(a)&&a.length!==b.length)errors.push(path+'.length');for(const key of Object.keys(a))compare(a[key],b[key],path+'.'+key);}
        else if(a!==b)errors.push(path);
      }
      compare(fixture.outcomes,result.outcomes,'outcomes');compare(fixture.metrics,result.metrics,'metrics');compare(fixture.traffic,result.traffic,'traffic');
      checks.push({model:fixture.settings.model,free:fixture.settings.initial_free_count,scheduled_changes:fixture.settings.interventions?.length??0,passed:errors.length===0,max_error:maxError,errors});
    }
    report={passed:checks.every(c=>c.passed),checks,source_bundle_sha256:manifest.bundle_sha256,scope:'Native/browser outcomes, aggregate metrics and complete traffic episodes; tolerance 1e-8; not empirical validation'};
    status.textContent=JSON.stringify(report,null,2);document.getElementById('save').disabled=false;
    engine.worker.terminate();
  }catch(e){status.textContent=String(e);}finally{document.getElementById('start').disabled=false;}
};
document.getElementById('save').onclick=()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='supply-traffic-browser-verification.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
