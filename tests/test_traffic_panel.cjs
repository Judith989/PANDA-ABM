// Run the real traffic-panel function: a ReferenceError here aborts simulation startup.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('dashboard/app.js','utf8');
const update=source.slice(source.indexOf('function updateTraffic(){'),source.indexOf('function downloadCongestion(){'));
function check(through,enabled=true){
 const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',value:'',checked:false});return elements.get(id)};
 const frame={traffic:{enabled,queues:{},cumulative_delay_s:0,aisle_delay_s:{},aisle_peak_queue:{},episodes:[],jam_episodes:[]},through_traffic:through,supply:{free:10,occupied:0,closed:0,closed_occupied:0,usable_inventory:10}};
 const context={$:el,state:{run:{tracks:[]},time:0,networks:[]},telemetryAt:()=>frame,trajectoryEntity:null,window:{PandaFollowCamera:{selectedDriver:()=>null}},esc:String,reasonLabel:String};
 vm.runInNewContext(update+'\nupdateTraffic();',context);
 return el('traffic-status').textContent;
}
assert.match(check({level:'medium',active:2,waiting_entry:1,completed:3}),/through traffic: 2 moving, 1 waiting outside, 3 completed/);
assert.doesNotMatch(check({level:'off'}),/through traffic:/);
assert.doesNotThrow(()=>check(undefined));
assert.match(check(undefined,false),/disabled/);
console.log('Traffic-panel startup regression: 4 cases passed.');
