const assert=require('node:assert/strict');require('../dashboard/motion.js');
const {interpolate,laneOffset,onSegment}=globalThis.PandaMotion;
const edges=[[[0,0],[2,0]],[[2,0],[2,2]]];
const a=[0,0,0,'searching',null,0,[]],b=[1,2,2,'searching',null,1,[[0,0],[2,0],[2,2]]];
assert.deepEqual(interpolate(a,b,.5,edges),{x:2,y:0,direction:[1,0]});
assert.deepEqual(interpolate(a,b,.75,edges),{x:2,y:1,direction:[0,1]});
for(let i=0;i<=100;i++){const p=interpolate(a,b,i/100,edges);assert(edges.some(([x,y])=>onSegment([p.x,p.y],x,y)));}
assert.deepEqual(interpolate([0,0,0,'searching',null,0],[1,2,2,'searching',null,1],.5,edges),{x:0,y:0,direction:[0,0]});
const straight=interpolate([0,0,0,'searching',null,0],[1,2,0,'searching',null,1],.5,edges);assert.equal(straight.x,1);assert.equal(straight.y,0);
assert.deepEqual(laneOffset([1,0],[1,0],[{a:[0,0],b:[2,0],spur:false}]),[0,-1.2]);
assert.deepEqual(laneOffset([1,0],[1,0],[{a:[0,0],b:[2,0],spur:true}]),[0,0]);
// Display separation: stacked vehicles are drawn apart; vehicles that do not touch are left alone.
const {separate}=globalThis.PandaMotion;
const stacked=separate([{id:'D1',x:0,y:0,direction:[1,0],type:'sedan'},{id:'D2',x:.2,y:0,direction:[1,0],type:'sedan'}]);
assert.equal(stacked.size,1);assert(stacked.has('D1'),'the vehicle behind gives way');assert(stacked.get('D1')[0]<=.2-4.55,'drawn a full car length behind');
const passing=separate([{id:'D1',x:0,y:1.2,direction:[-1,0],type:'sedan'},{id:'D2',x:0,y:-1.2,direction:[1,0],type:'sedan'}]);
assert.equal(passing.size,0,'opposite lanes 2.4 m apart are not overlaps');
const crossing=separate([{id:'D1',x:0,y:0,direction:[1,0],type:'truck'},{id:'D2',x:0,y:.5,direction:[0,1],type:'compact'}]);
assert.equal(crossing.size,1);
const queue=separate([0,.1,.2,.3].map((x,i)=>({id:'D'+i,x,y:0,direction:[1,0],type:'sedan'})));
const xs=[0,1,2,3].map(i=>(queue.get('D'+i)??[[0,.1,.2,.3][i]])[0]).sort((a,b)=>a-b);
for(let i=1;i<xs.length;i++)assert(xs[i]-xs[i-1]>=4.55-1e-6,'a stacked queue is drawn as separate cars');
assert.equal(separate([]).size,0);
console.log('Motion interpolation follows corners; legacy replay never cuts them; lane offsets respect bay approaches; overlapping vehicles are drawn apart.');
