/* A worker owns the original Python model. UI timing never advances model time. */
window.PandaEngine=class {
  constructor(onEvent=()=>{}){this.onEvent=onEvent;this.pending=new Map();this.sequence=0;this.start();}
  start(){
    this.worker=new Worker('engine/worker.js?v=20261107r1',{type:'module'});
    this.worker.onmessage=({data})=>{
      if(data.type){this.onEvent(data);return;}
      const call=this.pending.get(data.id);if(!call)return;this.pending.delete(data.id);
      data.error?call.reject(Error(data.error)):call.resolve(data.result);
    };
    this.worker.onerror=event=>{for(const call of this.pending.values())call.reject(Error(event.message||'The simulation worker stopped.'));this.pending.clear();this.onEvent({type:'error',message:event.message});};
  }
  request(method,payload={}){return new Promise((resolve,reject)=>{const id=++this.sequence;this.pending.set(id,{resolve,reject});this.worker.postMessage({id,method,payload});});}
  cancel(){this.worker.terminate();for(const call of this.pending.values())call.reject(Error('Simulation cancelled.'));this.pending.clear();this.start();}
};
