'use strict';
const e=id=>document.getElementById(id);
let viewer, route=[], looping=false, current=null, drag=null, busy=false, mode='pan';
let displayed=[];
const types=['rmc','gga','ais1','ais5'];
const inputForType={rmc:'rmc',gga:'gga',ais1:'ais_type1',ais5:'ais_type5'};
let configLoaded=false;
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
function setMode(next){mode=next;document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===mode));
  e('hint').textContent=({pan:'地図を操作できます。開始位置や航路点はドラッグして変更できます。',position:'地図をクリックすると送信位置が移動します。送信中も反映します。',waypoint:'地図をクリックするたび航路点を追加します。指定順に航行します。',heading:'地図をクリックして現在位置からの針路を指定します。既存の航路は解除します。'})[mode]}
async function api(path,body){const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});if(!response.ok)throw Error((await response.text()).slice(0,250));return response.json()}
function error(err){e('error').textContent=err.message||String(err)}
function mapCoords(screen){const ray=viewer.camera.getPickRay(screen),cart=ray&&viewer.scene.globe.pick(ray,viewer.scene);if(!cart)return null;const p=Cesium.Cartographic.fromCartesian(cart);const lat=round(Cesium.Math.toDegrees(p.latitude)),lon=round(Cesium.Math.toDegrees(p.longitude));return Number.isFinite(lat)&&Number.isFinite(lon)&&Math.abs(lat)<=89?{lat,lon}:null}
function bearing(from,to){const a=Cesium.Math.toRadians(from.lat),b=Cesium.Math.toRadians(to.lat),d=Cesium.Math.toRadians(to.lon-from.lon);return (Cesium.Math.toDegrees(Math.atan2(Math.sin(d)*Math.cos(b),Math.cos(a)*Math.sin(b)-Math.sin(a)*Math.cos(b)*Math.cos(d)))+360)%360}
function renderList(){const list=e('waypoints');list.replaceChildren();if(!route.length){list.textContent='航路点 0 件（地図上で追加）';return}route.forEach((p,i)=>{const div=document.createElement('div');div.className='waypoint';const label=document.createElement('span');label.textContent=`${i+1}. ${p.lat.toFixed(5)}°, ${p.lon.toFixed(5)}°`;const button=document.createElement('button');button.type='button';button.textContent='削除';button.setAttribute('aria-label',`航路点${i+1}を削除`);button.onclick=()=>applyRoute(route.filter((_,j)=>j!==i));div.append(label,button);list.append(div)})}
async function applyRoute(next){busy=true;try{const status=await api('/api/route',{waypoints:next,loop:looping});route=status.config.route.waypoints;current=status;renderList();renderMap(status)}catch(err){error(err)}finally{busy=false}}
async function applyPosition(pos){busy=true;try{const s=await api('/api/position',pos);e('latitude').value=pos.lat;e('longitude').value=pos.lon;current=s;renderMap(s)}catch(err){error(err)}finally{busy=false}}
function removeEntities(){displayed.forEach(item=>viewer.entities.remove(item));displayed=[]}
function addPoint(id,lon,lat,color,label,size){const entity=viewer.entities.add({id,position:Cesium.Cartesian3.fromDegrees(lon,lat),point:{pixelSize:size,color,outlineColor:Cesium.Color.BLACK,outlineWidth:2,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND},label:{text:label,font:'12px sans-serif',fillColor:Cesium.Color.WHITE,showBackground:true,pixelOffset:new Cesium.Cartesian2(0,-22)}});displayed.push(entity);return entity}
function renderMap(status){if(!viewer||drag)return;removeEntities();const p=status.position,course=status.course;
  if(route.length){const coords=[p,...route.slice(Math.min(status.route_index,route.length-1))].flatMap(q=>[q.lon,q.lat]);if(coords.length>=4)displayed.push(viewer.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray(coords),width:3,material:Cesium.Color.YELLOW.withAlpha(.9)}}))}
  const r=Cesium.Math.toRadians(course),d=.025;
  const dest=[p.lon+d*Math.sin(r)/Math.max(.1,Math.cos(Cesium.Math.toRadians(p.lat))),p.lat+d*Math.cos(r)];
  displayed.push(viewer.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray([p.lon,p.lat,...dest]),width:3,material:Cesium.Color.TURQUOISE}}));
  for(const vessel of status.vessels){if(vessel.mmsi===431234567)continue;addPoint('sim-ship-'+vessel.mmsi,vessel.lon,vessel.lat,Cesium.Color.CORNFLOWERBLUE,String(vessel.mmsi),9)}
  route.forEach((q,i)=>addPoint('sim-waypoint-'+i,q.lon,q.lat,Cesium.Color.YELLOW,'WP'+(i+1),11));
  addPoint('sim-start',p.lon,p.lat,Cesium.Color.TURQUOISE,'送信位置',15);
}
function updateStatus(s){current=s;route=s.config.route.waypoints;looping=s.config.route.loop;renderList();
  if(!configLoaded){for(const key of Object.values(inputForType))e(key).checked=s.config[key];updateTypeTabs();configLoaded=true}
  e('connection').textContent=s.active?(s.connected?'TCP接続中':'再接続中'):'停止中';e('target').textContent=s.target;e('lines').textContent=s.lines;
  e('position').textContent=s.position.lat.toFixed(5)+'°, '+s.position.lon.toFixed(5)+'°';e('currentMotion').textContent=s.course.toFixed(1)+'° / '+s.current_speed.toFixed(1)+' kt';
  e('routeProgress').textContent=s.route_done?'到着':route.length?`${Math.min(s.route_index+1,route.length)} / ${route.length}`:'航路なし';
  e('preview').textContent=s.preview.join('\n')||'送信待機中';e('error').textContent=s.error||'';
  renderMap(s)}
async function refresh(){if(busy||drag)return;try{updateStatus(await api('/api/status'))}catch(err){error(err)}}
function initMap(){if(!window.Cesium){e('error').textContent='Cesiumの読み込みに失敗しました';return}
  viewer=new Cesium.Viewer('map',{baseLayer:false,baseLayerPicker:false,geocoder:false,timeline:false,animation:false,navigationHelpButton:false,sceneModePicker:true,terrainProvider:new Cesium.EllipsoidTerrainProvider()});
  viewer.scene.globe.baseColor=Cesium.Color.fromCssColorString('#173549');
  viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(139.75,35.65,450000)});
  Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII')).then(provider=>viewer.imageryLayers.addImageryProvider(provider)).catch(error);
  const handler=viewer.screenSpaceEventHandler;
  handler.setInputAction(async event=>{if(drag)return;const p=mapCoords(event.position);if(!p||!current)return;
    if(mode==='position')await applyPosition(p);
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
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>setMode(button.dataset.mode));
e('removeLast').onclick=()=>applyRoute(route.slice(0,-1));e('clearRoute').onclick=()=>applyRoute([]);
e('loop').onchange=()=>{looping=e('loop').checked;applyRoute(route)};
e('config').onsubmit=async event=>{event.preventDefault();const data={};for(const key of ['latitude','longitude','course','speed','interval','vessel_count'])data[key]=Number(e(key).value);
  for(const key of Object.values(inputForType))data[key]=e(key).checked;
  data.gps=true;data.ais=true;data.route={waypoints:route,loop:e('loop').checked};busy=true;try{updateStatus(await api('/api/start',data))}catch(err){error(err)}finally{busy=false}};
e('stop').onclick=async()=>{busy=true;try{updateStatus(await api('/api/stop',{}))}catch(err){error(err)}finally{busy=false}};
initMap();refresh();setInterval(refresh,1000);
