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
console.log('Motion interpolation follows corners; legacy replay never cuts them; lane offsets respect bay approaches.');
