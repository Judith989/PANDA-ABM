const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 const root='paper/platform_evaluation/traffic_monitoring_20261105';
 const record=JSON.parse(fs.readFileSync(root+'/original_cpt.json','utf8'));
 const source=fs.readFileSync('dashboard/app.js','utf8');const start=source.indexOf('function downloadCongestion(){'),end=source.indexOf('async function refreshHistory(',start);assert(start>=0&&end>start);
 const helper=source.slice(source.indexOf('function segmentInfo('),source.indexOf('function segmentLink('));
 let blob,filename;const context={window:{},state:{time:180,id:'verification',run:{traffic:record.traffic}},telemetryAt:()=>({traffic:record.traffic}),$:()=>({textContent:''}),Blob,URL:{createObjectURL:b=>(blob=b,'blob:unit-test'),revokeObjectURL(){}},document:{createElement:()=>({set download(v){filename=v;},click(){}})},setTimeout:()=>0};
 vm.runInNewContext(helper+source.slice(start,end)+';downloadCongestion();',context);
 const csv=await blob.text();assert(filename.includes('congestion'));assert(csv.startsWith('"minimum_queued_vehicles"'));assert(csv.includes('"road_name"'));assert(csv.includes('"segment_label"'));fs.writeFileSync(root+'/exported_jams.csv',csv);
 fs.writeFileSync(root+'/csv_export_verification.json',JSON.stringify({status:'passed',scope:'Actual CSV export function executed with recorded audit snapshot; no browser UI interaction',expected_jams:record.traffic.jam_episodes.length,filename},null,2));
 console.log('Actual dashboard CSV export function produced the jam table.');
})();
