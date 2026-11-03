/* Static Vercel build: no Python installation or simulation server required. */
import { createHash } from 'node:crypto';
import { cp, mkdir, readFile, writeFile, rm, lstat } from 'node:fs/promises';
import { dirname, resolve, join, basename, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const release=join(root,'web','release'), output=join(root,'web','dist');
const offline=process.argv.includes('--offline');
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifest=JSON.parse(await readFile(join(release,'engine','manifest.json'),'utf8'));

for(const [relative,expected] of Object.entries(manifest.source_sha256)){
  const file=resolve(root,relative);
  if(!file.startsWith(root+sep))throw Error('Invalid source path in manifest');
  if(sha(await readFile(file))!==expected)throw Error(`Simulation source changed: ${relative}. Refresh the release with scripts/prepare_vercel_release.py.`);
}
for(const [relative,expected] of Object.entries(manifest.interface_sha256)){
  if(sha(await readFile(join(root,'dashboard',relative)))!==expected)throw Error(`Interface changed: ${relative}. Refresh the release snapshot before deployment.`);
}
if(sha(await readFile(join(release,'engine','python-source.zip')))!==manifest.bundle_sha256)throw Error('Simulation bundle checksum mismatch');

// Only this explicitly resolved generated directory may be removed.
if(dirname(output)!==join(root,'web')||basename(output)!=='dist')throw Error('Invalid build destination');
const old=await lstat(output).catch(()=>null);
if(old?.isSymbolicLink())throw Error('Build destination must not be a symbolic link');
await rm(output,{recursive:true,force:true});await mkdir(output,{recursive:true});
await cp(release,output,{recursive:true});
for(const relative of ['index.html','app.js','style.css','platform.js','platform.css','platform-views.html','THIRD_PARTY.md','engine/client.js','engine/worker.js']){
  const target=join(output,relative);await mkdir(dirname(target),{recursive:true});
  await cp(join(root,'dashboard',relative),target);
}

let runtimeBytes=0;
for(const [name,expected] of Object.entries(manifest.runtime_sha256)){
  if(basename(name)!==name)throw Error('Invalid runtime filename');
  let bytes;
  const checkedIn=join(release,'engine','runtime',name);
  bytes=await readFile(checkedIn).catch(()=>null);
  if(!bytes&&offline)bytes=await readFile(join(root,'dashboard','engine','runtime',name));
  if(!bytes){
    const url=`https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/${name}`;
    let last;
    for(let attempt=0;attempt<3;attempt++){
      try{const response=await fetch(url,{signal:AbortSignal.timeout(120000)});if(!response.ok)throw Error(`HTTP ${response.status}`);bytes=Buffer.from(await response.arrayBuffer());break;}
      catch(error){last=error;}
    }
    if(!bytes)throw Error(`Runtime download failed: ${name}: ${last.message}`);
  }
  if(sha(bytes)!==expected)throw Error(`Runtime checksum mismatch: ${name}`);
  const target=join(output,'engine','runtime',name);await mkdir(dirname(target),{recursive:true});await writeFile(target,bytes);runtimeBytes+=bytes.length;
}
for(const relative of ['index.html','assets/walmart_building.glb','assets/parking_asphalt.glb','scene.json','reference.json','study-results.json','engine/worker.js','engine/native-fixtures.json','engine/full-size-fixture.json'])await readFile(join(output,relative));
console.log(JSON.stringify({status:'verified',output:'web/dist',offline,python_bundle_sha256:manifest.bundle_sha256,runtime_bytes:runtimeBytes}));
