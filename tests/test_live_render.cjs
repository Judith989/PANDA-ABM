const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
// Through vehicles waiting outside the network have tracks without samples.
const source=fs.readFileSync('dashboard/app.js','utf8'),start=source.indexOf('function sample(');
const code=source.slice(start,source.indexOf('\nfunction ',start+1));
const context={window:{PandaMotion:{interpolate:(a)=>({x:a[1],y:a[2],direction:[0,0]})}},lastAt:()=>0,state:{run:{aisle_edges:[]}}};
vm.runInNewContext(code+';this.sample=sample;',context);
assert.equal(context.sample({samples:[]},12).state,'not_arrived');
assert.equal(context.sample({samples:[[0,4,5,'searching',null,0]]},0).x,4);
// Legacy replays draw walks along the walking network, never straight across bays.
require('../dashboard/pedestrians.js');const P=globalThis.PandaPedestrians;
const network={nodes:{a:[0,0],b:[0,10],c:[14,10],d:[14,0]},edges:[{from:'a',to:'b'},{from:'b',to:'c'},{from:'c',to:'d'}],
  space_access:{s:{node:'a',points:[[0,-3],[0,0]]}},destination_access:{door_2:'d'}};
const track={door:'door_2',samples:[[0,0,-3,'parked','s',0],[1,0,-3,'walking_to_destination','s',0],[31,0,-3,'at_destination','s',0],[100,0,-3,'returning_to_vehicle','s',0],[130,0,-3,'exiting','s',0]]};
const legs=P.legacyIntervals(track,[{id:'s',local_x_m:0,local_y_m:-3}],[{id:'door_2',local_x_m:14,local_y_m:0}],1.4,network);
const outbound=legs.filter(l=>l.phase==='to_door');
assert.deepEqual(outbound.map(l=>l.to_m),[[0,0],[0,10],[14,10],[14,0]]);
assert.equal(outbound[0].start_s,1);assert(Math.abs(outbound.at(-1).end_s-31)<1e-9);
assert.deepEqual(legs.filter(l=>l.phase==='to_vehicle').at(-1).to_m,[0,-3]);
assert.equal(P.position(legs,16).y,10);
console.log('Live render: tracks without samples are hidden; legacy walks follow the walking network.');
