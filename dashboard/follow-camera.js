/* Camera follow uses a position anchor; it does not wait for a GLB bounding sphere. */
(function(root){
  function selectedDriver(dropdown,inspection){if(dropdown)return dropdown;const [kind,id]=(inspection??'').split(':');return ['driver','parked','pedestrian'].includes(kind)?id:null;}
  function create(C,viewer,onStatus=()=>{}){
    let active=null,lastMessage='';
    const message=text=>{if(text!==lastMessage){lastMessage=text;onStatus(text);}};
    function stop(){if(active)viewer.camera.lookAtTransform(C.Matrix4.IDENTITY);active=null;viewer.trackedEntity=undefined;}
    function update({enabled,id,kind,position,waiting=false,finished=false,arrival='',label=''}){
      if(!enabled){stop();message('Camera follow is off.');return;}
      if(!id){stop();message('Select a driver to follow.');return;}
      if(waiting){stop();message(`${id} has not arrived${arrival?' · arrival '+arrival:''}. Tracking starts on arrival.`);return;}
      if(finished){stop();message(`${id} has left. Select another driver or rewind the replay.`);return;}
      if(!position){stop();message(`Waiting for ${id}'s position…`);return;}
      if(viewer.scene.mode!==C.SceneMode.SCENE3D)viewer.scene.morphTo3D(0);
      viewer.trackedEntity=undefined;
      const changed=!active||active.id!==id||active.kind!==kind;
      if(changed)viewer.camera.cancelFlight?.();
      const range=changed?(kind==='pedestrian'||kind==='destination'?14:32):Math.max(5,Math.min(150,C.Cartesian3.distance(viewer.camera.positionWC,active.position)));
      const heading=changed?0:viewer.camera.heading,pitch=changed?-.65:Math.max(-1.45,Math.min(-.15,viewer.camera.pitch));
      viewer.camera.lookAt(position,new C.HeadingPitchRange(heading,pitch,range));
      active={id,kind,position:C.Cartesian3.clone(position)};
      message(`Following ${id} · ${label||kind}. Uncheck follow for a free camera.`);
    }
    return {update,stop};
  }
  root.PandaFollowCamera={create,selectedDriver};
})(typeof window==='undefined'?globalThis:window);
