import {loadPyodide} from './runtime/pyodide.mjs';
let python, ready;
function progress(message){self.postMessage({type:'progress',message});}
async function initialize(){
  const start=performance.now();progress('Loading Python…');
  python=await loadPyodide({indexURL:new URL('runtime/',import.meta.url).href});
  progress('Loading scientific packages…');await python.loadPackage(['numpy','pandas','scipy']);
  const manifest=await (await fetch(new URL('manifest.json',import.meta.url),{cache:'no-cache'})).json();
  const response=await fetch(new URL('python-source.zip',import.meta.url),{cache:'no-cache'});
  if(!response.ok)throw Error('The simulation source bundle could not be loaded.');
  const source=await response.arrayBuffer();
  const digest=[...new Uint8Array(await crypto.subtle.digest('SHA-256',source))].map(b=>b.toString(16).padStart(2,'0')).join('');
  if(digest!==manifest.bundle_sha256)throw Error('Simulation source integrity check failed. Reload the site.');
  python.unpackArchive(source,'zip',{extractDir:'/work'});
  python.globals.set('_report',(done,total,model,information,seed)=>self.postMessage({type:'comparison-progress',done,total,model,information,seed}));
  await python.runPythonAsync(`import sys,json\nsys.path.insert(0,'/work')\nfrom panda_abm.twin.replay import LiveSimulation,record_run\nfrom panda_abm.twin.platform import simulate,compare,runtime_versions\n_live=None`);
  const runtime=JSON.parse(python.runPython('json.dumps(runtime_versions())'));
  self.postMessage({type:'ready',runtime,initialize_ms:performance.now()-start,manifest});
}
self.onmessage=async({data:{id,method,payload}})=>{
  try{
    ready??=initialize();await ready;python.globals.set('_payload_json',JSON.stringify(payload??{}));
    const code={
      ready:'json.dumps(runtime_versions())',
      summary:'json.dumps(simulate(json.loads(_payload_json)),allow_nan=False)',
      compare:'json.dumps(compare(json.loads(_payload_json),_report),allow_nan=False)',
      record:'json.dumps(record_run(json.loads(_payload_json)),allow_nan=False)',
      live:"_live=LiveSimulation(json.loads(_payload_json))\n_result=json.dumps(_live.describe(),allow_nan=False)",
      advance:"_result=json.dumps(_live.advance(json.loads(_payload_json)['seconds']),allow_nan=False)",
      close:"_live=None\n_result=json.dumps({'closed':True})"
    }[method];
    if(!code)throw Error('Unknown simulation operation');
    const result=await python.runPythonAsync(code);
    self.postMessage({id,result:JSON.parse(result??python.globals.get('_result'))});
  }catch(error){self.postMessage({id,error:String(error)});}
};
