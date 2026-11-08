const assert=require('node:assert/strict');require('../dashboard/pedestrians.js');const P=globalThis.PandaPedestrians;
const legs=[{phase:'to_door',start_s:10,end_s:20,from_m:[0,0],to_m:[14,0]},{phase:'to_vehicle',start_s:100,end_s:110,from_m:[14,0],to_m:[0,0]}];
assert.equal(P.position(legs,9),null);assert.equal(P.position(legs,20),null);assert.equal(P.position(legs,50),null);assert.equal(P.position(legs,110),null);
assert.equal(P.position(legs,15).x,7);assert.equal(P.position(legs,105).x,7);assert.deepEqual(P.position(legs,105).direction,[-1,0]);
assert.deepEqual(P.position(legs,15),P.position(legs,15)); // Paused time holds the same position.
const track={door:'door_2',samples:[[0,0,0,'parked','s',0],[11,0,0,'walking_to_destination','s',0],[21,0,0,'at_destination','s',0],[101,0,0,'returning_to_vehicle','s',0],[111,0,0,'exiting','s',0]]};
const fallback=P.legacyIntervals(track,[{id:'s',local_x_m:0,local_y_m:0}],[{id:'door_2',local_x_m:14,local_y_m:0}]);assert.equal(fallback.length,2);assert.equal(P.position(fallback,16).x,7);assert.equal(P.position(fallback,106).x,7);
console.log('Pedestrian paths reach the selected door, return to the vehicle, and freeze when simulation time is paused.');

const observed=[{phase:'to_door',start_s:1,end_s:2,from_m:[0,0],to_m:[1.4,0],source:'simulated_network_walk'},{phase:'to_door',start_s:2,end_s:3,from_m:[1.4,0],to_m:[1.4,0],waiting:true,source:'simulated_network_walk'},{phase:'to_door',start_s:3,end_s:4,from_m:[1.4,0],to_m:[1.4,1.4],source:'simulated_network_walk'}];
assert.equal(P.position(observed,2.5).x,1.4);assert.equal(P.position(observed,2.5).y,0);
assert.equal(P.position(observed,3.5).x,1.4);assert.ok(Math.abs(P.position(observed,3.5).y-.7)<1e-12);
assert.equal(P.position(observed,4).y,1.4);assert.equal(P.position(observed,4.1),null);
// A live walk recorded only up to the previous second stays visible while the driver is walking.
const partial=[{phase:'to_door',start_s:10,end_s:11,from_m:[0,0],to_m:[1.4,0],source:'simulated_network_walk'}];
assert.equal(P.position(partial,11.6),null);
assert.equal(P.position(partial,11.6,true).x,1.4);
assert.equal(P.position(partial,9,true),null);
console.log('Network bends, stationary waits and live-frame endpoint display passed.');
