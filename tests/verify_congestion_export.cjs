const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
(async()=>{
 // Uses the archived audit snapshot when present; otherwise a minimal recorded-format fixture.
 const root='paper/platform_evaluation/traffic_monitoring_20261105',archived=fs.existsSync(root+'/original_cpt.json');
 const causes={following_vehicle:3,red_signal:2};
 const record=archived?JSON.parse(fs.readFileSync(root+'/original_cpt.json','utf8')):{traffic:{enabled:true,episodes:[],jam_episodes:[
   {minimum_queued_vehicles:2,aisle:'street_2_1',start_s:31,end_s:48,duration_s:17,peak_queue:2,queued_vehicle_delay_s:21.5,causes,cause_vehicle_seconds:causes,cause_active_seconds:causes},
   {minimum_queued_vehicles:2,aisle:'cross_1_0',start_s:90,end_s:null,duration_s:12,peak_queue:3,queued_vehicle_delay_s:30,causes:{junction_yield:4},cause_vehicle_seconds:{junction_yield:4},cause_active_seconds:{junction_yield:4}}]}};
 const source=fs.readFileSync('dashboard/app.js','utf8');const start=source.indexOf('function downloadCongestion(){'),end=source.indexOf('async function refreshHistory(',start);assert(start>=0&&end>start);
 const helper=source.slice(source.indexOf('function segmentInfo('),source.indexOf('function segmentLink('));
 let blob,filename;const context={window:{},state:{time:180,id:'verification',run:{traffic:record.traffic}},telemetryAt:()=>({traffic:record.traffic}),$:()=>({textContent:''}),Blob,URL:{createObjectURL:b=>(blob=b,'blob:unit-test'),revokeObjectURL(){}},document:{createElement:()=>({set download(v){filename=v;},click(){}})},setTimeout:()=>0};
 vm.runInNewContext(helper+source.slice(start,end)+';downloadCongestion();',context);
 const csv=await blob.text();assert(filename.includes('congestion'));assert(csv.startsWith('"minimum_queued_vehicles"'));assert(csv.includes('"road_name"'));assert(csv.includes('"segment_label"'));
 assert.equal(csv.split('\r\n').length,record.traffic.jam_episodes.length+1);
 if(archived){
   fs.writeFileSync(root+'/exported_jams.csv',csv);
   fs.writeFileSync(root+'/csv_export_verification.json',JSON.stringify({status:'passed',scope:'Actual CSV export function executed with recorded audit snapshot; no browser UI interaction',expected_jams:record.traffic.jam_episodes.length,filename},null,2));
 }
 console.log(`Actual dashboard CSV export function produced the jam table (${archived?'archived audit snapshot':'built-in fixture'}).`);
})().catch(error=>{console.error(error);process.exit(1);});
