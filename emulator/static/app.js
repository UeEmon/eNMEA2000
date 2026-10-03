'use strict';
const e=id=>document.getElementById(id);
let viewer, route=[], looping=false, current=null, drag=null, busy=false, mode='pan';
let displayed=[];
const types=['rmc','gga','ais1','ais5'];
const inputForType={rmc:'rmc',gga:'gga',ais1:'ais_type1',ais5:'ais_type5'};
const ais5Fields=['repeat','ais_version','imo','callsign','shipname','ship_type','to_bow','to_stern','to_port','to_starboard','epfd','month','day','hour','minute','draught','destination','dte'];
const ais5Text=['callsign','shipname','destination'];
let configLoaded=false;
let aisScenarios=[];
let suiteMarkers=[];
let motionLoaded=false;
function applyMotion(state){
  if(state.active||(!motionLoaded&&state.markers.length)){
    suiteMarkers=state.markers;e('suiteLat').value=state.center.lat;e('suiteLon').value=state.center.lon;e('suiteSpacing').value=state.spacing_nm}
  motionLoaded=true;
  for(const id of ['suiteLat','suiteLon','suiteSpacing','sendAllScenarios'])e(id).disabled=state.active;
  e('mapMode').querySelector('option[value="suite-center"]').disabled=state.active;
  e('ringMotionStatus').textContent=(state.active?(state.connected?'周回送信中':'TCP再接続中'):'周回停止中')+
    (state.markers.length?` · 更新 ${state.interval.toFixed(2)}秒 / ${state.angular_step_deg.toFixed(3)}° · 外周移動 ${(state.movement_nm.at(-1).distance*1852).toFixed(1)}m/更新`:'')+
    (state.error?' · '+state.error:'');
  if(state.active&&mode==='suite-center')setMode('pan');
}
function ringRequest(){const center=suiteCenter(),spacing=Number(e('suiteSpacing').value);
  if(!Number.isFinite(center.lat)||Math.abs(center.lat)>89||!Number.isFinite(center.lon)||Math.abs(center.lon)>180||!Number.isFinite(spacing)||spacing<.2||spacing>20)throw Error('中心座標または間隔を確認してください');
  return {scenario_ids:aisScenarios.map(item=>item.id),center,spacing_nm:spacing}}
async function startAllScenarios(){if(!aisScenarios.length)return;e('sendAllScenarios').disabled=true;
  try{const request=ringRequest(),state=await api('/api/ais/motion/start',request);applyMotion(state);if(current)renderMap(current);
    e('suiteResult').textContent=`全Type送信開始: ${state.sent}項目 / ${state.sentences}文 → ${state.target}（自動周回・位置更新を継続中）`;
    viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(request.center.lon,request.center.lat,Math.max(50000,request.spacing_nm*1852*28))})}
  catch(err){e('suiteResult').textContent=err.message;e('sendAllScenarios').disabled=false}}
async function stopAllSending(){const status=await api('/api/stop',{});suiteMarkers=status.motion.markers;applyMotion(status.motion);updateStatus(status);e('suiteResult').textContent='送信停止しました'}
e('stopRingMotion').onclick=async()=>{try{await stopAllSending()}catch(err){e('suiteResult').textContent=err.message}};
function suiteCenter(){return {lat:Number(e('suiteLat').value),lon:Number(e('suiteLon').value)}}
function setSuiteCenter(point){e('suiteLat').value=point.lat;e('suiteLon').value=point.lon;suiteMarkers=[];if(current)renderMap(current)}
function selectedAisScenario(){return aisScenarios.find(item=>item.id===e('aisScenario').value)}
function showAisScenario(){const item=selectedAisScenario();e('suiteFrames').textContent=item?.frames.join('\n')||''}
async function loadAisScenarios(){try{const data=await api('/api/ais/scenarios');aisScenarios=data.scenarios;
  const select=e('aisScenario');select.replaceChildren();for(const item of aisScenarios){const option=document.createElement('option');option.value=item.id;option.textContent=item.label+' · '+item.sentences+'文';select.append(option)}
  e('suiteCoverage').textContent=`${data.types.length} Type / ${aisScenarios.length}項目（分割・形式別を含む）`;showAisScenario()
}catch(err){e('suiteResult').textContent=err.message}}
async function sendAisScenarios(ids){const buttons=[e('sendScenario')];buttons.forEach(button=>button.disabled=true);
  try{const result=await api('/api/ais/send',{scenario_ids:ids});
    e('suiteResult').textContent=`TCP送信完了: ${result.sent}項目 / ${result.sentences}文 → ${result.target}`;refresh()}
  catch(err){e('suiteResult').textContent=`送信失敗: ${err.message}`}finally{buttons.forEach(button=>button.disabled=false)}}
e('aisScenario').onchange=showAisScenario;
e('sendScenario').onclick=()=>{if(selectedAisScenario())sendAisScenarios([e('aisScenario').value])};
e('sendAllScenarios').onclick=startAllScenarios;
for(const key of ['suiteLat','suiteLon','suiteSpacing'])e(key).addEventListener('change',()=>{suiteMarkers=[];if(current)renderMap(current)});
for(const key of ais5Text)e('ais5_'+key).addEventListener('input',event=>{event.target.value=event.target.value.toUpperCase()});
function activateTab(type){for(const name of types){const selected=name===type,tab=e('tab-'+name);tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;e('panel-'+name).hidden=!selected}}
function updateTypeTabs(){for(const name of types)e('tab-'+name).dataset.enabled=e(inputForType[name]).checked?'true':'false'}
document.querySelectorAll('[data-tab]').forEach(button=>{
  button.onclick=()=>activateTab(button.dataset.tab);
  button.onkeydown=event=>{const index=types.indexOf(button.dataset.tab);let next;
    if(event.key==='ArrowRight')next=(index+1)%types.length;
    else if(event.key==='ArrowLeft')next=(index+types.length-1)%types.length;
    else if(event.key==='Home')next=0;
    else if(event.key==='End')next=types.length-1;
    else return;
    event.preventDefault();activateTab(types[next]);e('tab-'+types[next]).focus()};
  e(inputForType[button.dataset.tab]).onchange=updateTypeTabs;
});
updateTypeTabs();
function round(n){return Number(n.toFixed(6))}
function setMode(next){mode=next;e('mapMode').value=mode;
  e('hint').textContent=({pan:'地図を操作できます。開始位置や航路点はドラッグして変更できます。',position:'地図をクリックすると送信位置が移動します。送信中も反映します。','suite-center':'地図をクリックすると全Type試験の中心を指定します。',waypoint:'地図をクリックするたび航路点を追加します。指定順に航行します。',heading:'地図をクリックして現在位置からの針路を指定します。既存の航路は解除します。'})[mode]}
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok)throw Error((await response.text()).slice(0,250));return response.json()}
function error(err){e('error').textContent=err.message||String(err)}
function mapCoords(screen){const ray=viewer.camera.getPickRay(screen),cart=ray&&viewer.scene.globe.pick(ray,viewer.scene);if(!cart)return null;const p=Cesium.Cartographic.fromCartesian(cart);const lat=round(Cesium.Math.toDegrees(p.latitude)),lon=round(Cesium.Math.toDegrees(p.longitude));return Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=89?{lat,lon}:null}
function bearing(from,to){const a=Cesium.Math.toRadians(from.lat),b=Cesium.Math.toRadians(to.lat),d=Cesium.Math.toRadians(to.lon-from.lon);return (Cesium.Math.toDegrees(Math.atan2(Math.sin(d)*Math.cos(b),Math.cos(a)*Math.sin(b)-Math.sin(a)*Math.cos(b)*Math.cos(d)))+360)%360}
function renderList(){const list=e('waypoints');list.replaceChildren();if(!route.length){list.textContent='航路点 0 件（地図上で追加）';return}route.forEach((p,i)=>{const div=document.createElement('div');div.className='waypoint';const label=document.createElement('span');label.textContent=`${i+1}. ${p.lat.toFixed(5)}°, ${p.lon.toFixed(5)}°`;const button=document.createElement('button');button.type='button';button.textContent='削除';button.setAttribute('aria-label',`航路点${i+1}を削除`);button.onclick=()=>applyRoute(route.filter((_,j)=>j!==i));div.append(label,button);list.append(div)})}
async function applyRoute(next){busy=true;try{const status=await api('/api/route',{waypoints:next,loop:looping});route=status.config.route.waypoints;current=status;renderList();renderMap(status)}catch(err){error(err)}finally{busy=false}}
async function applyPosition(pos){busy=true;try{const s=await api('/api/position',pos);e('latitude').value=pos.lat;e('longitude').value=pos.lon;current=s;renderMap(s)}catch(err){error(err)}finally{busy=false}}
function removeEntities(){displayed.forEach(item=>viewer.entities.remove(item));displayed=[]}
function addPoint(id,lon,lat,color,label,size){const entity=viewer.entities.add({id,position:Cesium.Cartesian3.fromDegrees(lon,lat),...(id.startsWith('sim-waypoint-')?{point:{pixelSize:size,color,outlineColor:Cesium.Color.BLACK,outlineWidth:2,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND}}:NmeaSymbols.graphics({own:id==='sim-start',simulation:true})),label:{text:label,font:'12px sans-serif',fillColor:Cesium.Color.WHITE,showBackground:true,pixelOffset:new Cesium.Cartesian2(0,id.startsWith('sim-waypoint-')?-22:-34)}});displayed.push(entity);return entity}
function renderMap(status){if(!viewer||drag)return;removeEntities();const p=status.position,course=status.course;
  if(route.length){const coords=[p,...route.slice(Math.min(status.route_index,route.length-1))].flatMap(q=>[q.lon,q.lat]);if(coords.length>=4)displayed.push(viewer.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray(coords),width:3,material:Cesium.Color.YELLOW.withAlpha(.9)}}))}
  const r=Cesium.Math.toRadians(course),d=.025;
  const dest=[p.lon+d*Math.sin(r)/Math.max(.1,Math.cos(Cesium.Math.toRadians(p.lat))),p.lat+d*Math.cos(r)];
  displayed.push(viewer.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray([p.lon,p.lat,...dest]),width:3,material:Cesium.Color.TURQUOISE}}));
  for(const vessel of status.vessels){if(vessel.mmsi===status.config.mmsi_start)continue;addPoint('sim-ship-'+vessel.mmsi,vessel.lon,vessel.lat,Cesium.Color.CORNFLOWERBLUE,String(vessel.mmsi),9)}
  route.forEach((q,i)=>addPoint('sim-waypoint-'+i,q.lon,q.lat,Cesium.Color.YELLOW,'WP'+(i+1),11));
  addPoint('sim-start',p.lon,p.lat,Cesium.Color.TURQUOISE,'送信位置',15);
  const center=suiteCenter();if(Number.isFinite(center.lat)&&Math.abs(center.lat)<=89&&Number.isFinite(center.lon)&&Math.abs(center.lon)<=180){
    addPoint('sim-suite-center',center.lon,center.lat,Cesium.Color.ORANGE,'試験中心',13);
    const spacing=Number(e('suiteSpacing').value);
    if(suiteMarkers.length&&Number.isFinite(spacing)){
      for(const ring of new Set(suiteMarkers.map(marker=>marker.ring)))
        displayed.push(viewer.entities.add({id:'sim-suite-ring-'+ring,position:Cesium.Cartesian3.fromDegrees(center.lon,center.lat),ellipse:{semiMajorAxis:ring*spacing*1852,semiMinorAxis:ring*spacing*1852,material:Cesium.Color.ORANGE.withAlpha(.04),outline:true,outlineColor:Cesium.Color.ORANGE.withAlpha(.6)}}));
      for(const marker of suiteMarkers){const entity=addPoint('sim-suite-'+marker.id,marker.lon,marker.lat,Cesium.Color.ORANGE,'T'+marker.message_type,10);
        entity.description=`${marker.label} / MMSI ${marker.mmsi} / ${marker.ring}周目`}
    }
  }
}
function hideQuickMenu(){e('quickMenu').hidden=true}
function quickAction(label,callback){const button=document.createElement('button');button.type='button';button.setAttribute('role','menuitem');button.textContent=label;
  button.onclick=()=>{hideQuickMenu();callback()};e('quickMenuActions').append(button)}
function showQuickMenu(screen){if(!current||busy||drag)return;
  const nearby=displayed.filter(entity=>typeof entity.id==='string'&&entity.position&&(entity.point||entity.billboard))
    .map(entity=>{const p=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,entity.position.getValue(viewer.clock.currentTime));
      return {id:entity.id,distance:p?Math.hypot(p.x-screen.x,p.y-screen.y):Infinity}})
    .filter(item=>item.distance<=18).sort((a,b)=>a.distance-b.distance);
  let id=nearby[0]?.id;
  if(!id){const hit=viewer.scene.pick(screen)?.id;id=hit?.id}
  if(typeof id!=='string'){hideQuickMenu();return}
  let point,title,index;
  if(id==='sim-start'){point={...current.position};title='送信位置'}
  else if(id.startsWith('sim-waypoint-')){index=Number(id.slice('sim-waypoint-'.length));point=route[index];title=`航路点 ${index+1}`}
  else if(id.startsWith('sim-ship-')){const mmsi=Number(id.slice('sim-ship-'.length));point=current.vessels.find(v=>v.mmsi===mmsi);title=`船舶 MMSI ${mmsi}`}
  if(!point){hideQuickMenu();return}
  const pos={lat:point.lat,lon:point.lon},menu=e('quickMenu'),actions=e('quickMenuActions');
  e('quickMenuTitle').textContent=title;e('quickMenuCoords').textContent=`${pos.lat.toFixed(5)}°, ${pos.lon.toFixed(5)}°`;actions.replaceChildren();
  quickAction('ここを地図の中心に表示',()=>viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(pos.lon,pos.lat,100000)}));
  if(id==='sim-start')quickAction('ここを航路点に追加',()=>applyRoute([...route,pos]));
  else if(index!==undefined){quickAction('ここを開始位置に設定',()=>applyPosition(pos));
    quickAction('この航路点を削除',()=>applyRoute(route.filter((_,i)=>i!==index)))}
  else quickAction('ここを開始位置に設定',()=>applyPosition(pos));
  menu.hidden=false;
  const card=e('map').parentElement,canvas=viewer.canvas,canvasRect=canvas.getBoundingClientRect(),cardRect=card.getBoundingClientRect();
  menu.style.left=Math.max(8,Math.min(canvasRect.left-cardRect.left+screen.x,card.clientWidth-menu.offsetWidth-8))+'px';
  menu.style.top=Math.max(8,Math.min(canvasRect.top-cardRect.top+screen.y,card.clientHeight-menu.offsetHeight-8))+'px';
  menu.querySelector('button')?.focus();
}
function updateStatus(s){current=s;route=s.config.route.waypoints;looping=s.config.route.loop;renderList();
  if(!configLoaded){for(const key of Object.values(inputForType))e(key).checked=s.config[key];updateTypeTabs();e('mmsi_start').value=s.config.mmsi_start;for(const key of ais5Fields)e('ais5_'+key).value=String(s.config.ais5[key]);configLoaded=true}
  e('connection').textContent=s.active?(s.connected?'TCP接続中':'再接続中'):'停止中';e('target').textContent=s.target;e('lines').textContent=s.lines;
  e('position').textContent=s.position.lat.toFixed(5)+'°, '+s.position.lon.toFixed(5)+'°';e('currentMotion').textContent=s.course.toFixed(1)+'° / '+s.current_speed.toFixed(1)+' kt';
  e('routeProgress').textContent=s.route_done?'到着':route.length?`${Math.min(s.route_index+1,route.length)} / ${route.length}`:'航路なし';
  e('preview').textContent=s.preview.join('\n')||'送信待機中';e('error').textContent=s.error||'';
  renderMap(s)}
async function refresh(){if(busy||drag)return;try{const [status,motion]=await Promise.all([api('/api/status'),api('/api/ais/motion')]);applyMotion(motion);updateStatus(status)}catch(err){error(err)}}
function initMap(){if(!window.Cesium){e('error').textContent='Cesiumの読み込みに失敗しました';return}
  viewer=new Cesium.Viewer('map',{baseLayer:false,baseLayerPicker:false,geocoder:false,timeline:false,animation:false,navigationHelpButton:false,sceneModePicker:true,terrainProvider:new Cesium.EllipsoidTerrainProvider()});
  viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString('#173549');
  viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(139.75,35.65,450000)});
  Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')).then(provider=>viewer.imageryLayers.addImageryProvider(provider)).catch(error);
  const handler=viewer.screenSpaceEventHandler;
  document.addEventListener('contextmenu',event=>{if(e('map').contains(event.target))event.preventDefault()},true);
  document.addEventListener('pointerup',event=>{if(event.button!==2||!e('map').contains(event.target))return;
    const rect=viewer.canvas.getBoundingClientRect();
    showQuickMenu(new Cesium.Cartesian2(event.clientX-rect.left,event.clientY-rect.top))},true);
  handler.setInputAction(async event=>{hideQuickMenu();if(drag)return;const p=mapCoords(event.position);if(!p||!current)return;
    if(mode==='position')await applyPosition(p);
    if(mode==='suite-center')setSuiteCenter(p);
    if(mode==='waypoint')await applyRoute([...route,p]);
    if(mode==='heading'){
      const course=round(bearing(current.position,p));busy=true;
      try{const clear=await api('/api/route',{waypoints:[],loop:false});const s=await api('/api/course',{course});route=[];looping=false;e('loop').checked=false;e('course').value=course;updateStatus(s);e('hint').textContent=`針路 ${course.toFixed(1)}° を設定しました`}
      catch(err){error(err)}finally{busy=false}
    }
  },Cesium.ScreenSpaceEventType.LEFT_CLICK);
  handler.setInputAction(event=>{if(mode!=='pan')return;const picked=viewer.scene.pick(event.position)?.id;if(!picked||!picked.id)return;
    if(picked.id==='sim-start')drag={kind:'start',entity:picked};
    else if(picked.id.startsWith('sim-waypoint-'))drag={kind:'waypoint',index:Number(picked.id.slice(13)),entity:picked};
    if(drag){drag.moved=false;viewer.scene.screenSpaceCameraController.enableRotate=false;e('map').classList.add('dragging')}
  },Cesium.ScreenSpaceEventType.LEFT_DOWN);
  handler.setInputAction(event=>{const p=mapCoords(event.endPosition);if(!p)return;e('mapPos').textContent=p.lat.toFixed(5)+'°, '+p.lon.toFixed(5)+'°';if(drag){drag.point=p;drag.entity.position=Cesium.Cartesian3.fromDegrees(p.lon,p.lat);drag.moved=true}},Cesium.ScreenSpaceEventType.MOUSE_MOVE);
  handler.setInputAction(async event=>{if(!drag)return;const completed=drag;drag=null;viewer.scene.screenSpaceCameraController.enableRotate=true;e('map').classList.remove('dragging');const p=mapCoords(event.position)||completed.point;if(!completed.moved||!p){if(current)renderMap(current);return}
    if(completed.kind==='start')await applyPosition(p);
    else{const edited=route.slice();edited[completed.index]=p;await applyRoute(edited)}
  },Cesium.ScreenSpaceEventType.LEFT_UP)
}
NmeaSymbols.bind(e('symbolStandard'),()=>{if(current)renderMap(current)});
e('mapMode').onchange=event=>setMode(event.target.value);
document.addEventListener('pointerdown',event=>{if(!e('quickMenu').contains(event.target))hideQuickMenu()});
document.addEventListener('keydown',event=>{if(event.key==='Escape')hideQuickMenu()});
e('removeLast').onclick=()=>applyRoute(route.slice(0,-1));e('clearRoute').onclick=()=>applyRoute([]);
e('loop').onchange=()=>{looping=e('loop').checked;applyRoute(route)};
e('config').onsubmit=async event=>{event.preventDefault();const data={};for(const key of ['latitude','longitude','course','speed','interval','vessel_count'])data[key]=Number(e(key).value);
  for(const key of Object.values(inputForType))data[key]=e(key).checked;
  data.mmsi_start=Number(e('mmsi_start').value);data.ais5={};for(const key of ais5Fields){const value=e('ais5_'+key).value;data.ais5[key]=ais5Text.includes(key)?value:key==='dte'?value==='true':Number(value)}
  data.gps=true;data.ais=true;data.route={waypoints:route,loop:e('loop').checked};busy=true;try{updateStatus(await api('/api/start',data))}catch(err){error(err)}finally{busy=false}};
e('stop').onclick=async()=>{busy=true;try{await stopAllSending()}catch(err){error(err)}finally{busy=false}};
initMap();refresh();loadAisScenarios();setInterval(refresh,1000);
