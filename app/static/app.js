'use strict';
const $=id=>document.getElementById(id);
let rows=[], paused=false, enabled=true, socket=null, timer=null, reconnect=null, active=false;
let globe=null, globeEntities=[], firstFix=true;
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',6500)}
async function api(url,options={}){const r=await fetch(url,options);if(r.status===401){disconnect();if(!$('login').open)$('login').showModal();throw Error('ログインが必要です')}if(!r.ok){let body=await r.json().catch(()=>({}));throw Error(body.detail||`HTTP ${r.status}`)}return r.json()}
function disconnect(){active=false;clearInterval(timer);clearTimeout(reconnect);if(socket){socket.onclose=null;socket.close();socket=null}$('light').className='';$('connection').textContent='未接続'}
function merge(data){const byId=new Map(rows.map(r=>[r.id,r]));for(const r of data)byId.set(r.id,r);rows=[...byId.values()].sort((a,b)=>b.id-a.id).slice(0,500);render()}
function filtered(){const search=$('search').value.toLowerCase(), source=$('source').value;return rows.filter(r=>(source==='all'||r.source.startsWith(source+':'))&&(!search||JSON.stringify(r).toLowerCase().includes(search)))}
function render(){if(paused)return;const view=filtered(),body=$('rows');body.replaceChildren();for(const row of view){const tr=document.createElement('tr');tr.dataset.id=row.id;const values=[new Date(row.received_at).toLocaleTimeString(),row.source.startsWith('udp:')?'UDP':(row.filename||'FILE'),row.sentence_type,row.status,row.raw];for(let i=0;i<values.length;i++){const td=document.createElement('td');if(i===3){const badge=document.createElement('span');badge.className='status '+row.status;badge.textContent=({ok:'正常',error:'エラー',pending:'断片待機',unsupported:'未対応'})[row.status]||row.status;td.append(badge)}else{td.textContent=values[i];td.title=String(values[i])}tr.append(td)}tr.onclick=()=>$('detail').textContent=JSON.stringify(row,null,2);body.append(tr)}draw(view)}
function draw(view){
  if(!globe)return;
  globeEntities.forEach(entity=>globe.entities.remove(entity));globeEntities=[];
  const pts=view.filter(r=>r.latitude!==null&&r.longitude!==null);
  const tracks=new Map();
  for(const row of [...pts].reverse()){
    const key=row.source+':'+(row.mmsi||'GPS');
    if(!tracks.has(key))tracks.set(key,[]);
    tracks.get(key).push(row);
  }
  let index=0;
  for(const [key,list] of tracks){
    const latest=list.at(-1), color=[Cesium.Color.TURQUOISE,Cesium.Color.CORNFLOWERBLUE,Cesium.Color.ORANGE,Cesium.Color.VIOLET][index++%4];
    const coords=list.map(p=>Cesium.Cartesian3.fromDegrees(p.longitude,p.latitude));
    if(coords.length>1)globeEntities.push(globe.entities.add({polyline:{positions:coords,width:2,material:color.withAlpha(.75)}}));
    const cog=Number(latest.decoded?.course??latest.decoded?.cog??latest.decoded?.true_course);
    const lon=latest.longitude,lat=latest.latitude;
    const description='MMSI '+(latest.mmsi||'自船')+' / '+latest.received_at;
    globeEntities.push(globe.entities.add({name:latest.mmsi||'GPS',description,
      position:Cesium.Cartesian3.fromDegrees(lon,lat),
      point:{pixelSize:10,color,outlineColor:Cesium.Color.BLACK,outlineWidth:2,heightReference:Cesium.HeightReference.CLAMP_TO_GROUND},
      label:{text:latest.mmsi||'GPS',font:'12px sans-serif',fillColor:Cesium.Color.WHITE,showBackground:true,
             pixelOffset:new Cesium.Cartesian2(0,-24),distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,3000000)}}));
    if(Number.isFinite(cog) && cog>=0 && cog<360){
      const d=.012,r=cog*Math.PI/180, nextLat=lat+d*Math.cos(r),nextLon=lon+d*Math.sin(r)/Math.max(.1,Math.cos(lat*Math.PI/180));
      globeEntities.push(globe.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray([lon,lat,nextLon,nextLat]),width:2,material:color}}));
    }
  }
  $('points').textContent=`${pts.length} ポイント / ${tracks.size} トラック`;
  if(firstFix&&pts.length){firstFix=false;const p=pts[0];globe.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(p.longitude,p.latitude,350000),duration:1.3})}
}
async function initGlobe(){
  if(!window.Cesium){toast('Cesiumの読み込みに失敗しました');return}
  globe=new Cesium.Viewer('cesium',{baseLayer:false,baseLayerPicker:false,geocoder:false,homeButton:true,
    navigationHelpButton:false,animation:false,timeline:false,sceneModePicker:true,terrainProvider:new Cesium.EllipsoidTerrainProvider()});
  globe.scene.globe.baseColor=Cesium.Color.fromCssColorString('#193349');
  globe.camera.setView({destination:Cesium.Cartesian3.fromDegrees(139.75,35.65,3000000)});
  try {
    const imagery=await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'));
    globe.imageryLayers.addImageryProvider(imagery);
  }catch(error){toast('地球の背景図を読み込めませんでした: '+error.message)}
  render();
}

async function refresh(){const [s,jobs]=await Promise.all([api('/api/stats'),api('/api/jobs')]);$('total').textContent=s.total.toLocaleString();$('success').textContent=(s.statuses.ok||0).toLocaleString();$('errors').textContent=(s.statuses.error||0).toLocaleString();$('datagrams').textContent=s.runtime.datagrams.toLocaleString();enabled=s.udp_enabled;$('toggle').textContent=enabled?'受信停止':'受信再開';$('udpStatus').textContent=`UDP ${s.udp_port} / TCP ${s.tcp_port} · ${enabled?'受信中':'停止中'} · TCP接続 ${s.runtime.tcp_connections}`;$('queue').textContent=`待機 ${s.queue_size} / AIS未完了 ${s.ais_pending}`;$('warning').textContent=`キュー破棄 ${s.runtime.queue_dropped} · DB保存失敗 ${s.runtime.db_errors} · AISタイムアウト ${s.ais_expired} · 配信破棄 ${s.runtime.ws_dropped}`;$('jobs').replaceChildren();for(const j of jobs.slice(0,8)){const el=document.createElement('div');el.className='job';const title=document.createElement('span');title.textContent=j.filename;el.append(title);if(['running','queued'].includes(j.status)){const b=document.createElement('button');b.textContent='停止';b.onclick=()=>api(`/api/jobs/${j.id}/cancel`,{method:'POST'}).catch(e=>toast(e.message));el.append(b)}const p=document.createElement('progress');p.max=Math.max(j.size,1);p.value=j.bytes_read;el.append(p);const sm=document.createElement('small');sm.textContent=`${j.status} · ${j.lines}行 · 正常 ${j.ok} / エラー ${j.error} / 未完了AIS ${j.incomplete_ais_groups||0}`;el.append(sm);$('jobs').append(el)}}
function connectWS(){if(!active)return;socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);socket.onopen=()=>{$('light').className='live';$('connection').textContent='LIVE / 接続中';api('/api/events?limit=500').then(merge).catch(e=>toast(e.message))};socket.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.type==='events')merge(msg.rows);if(msg.type==='gap')api('/api/events?limit=500').then(merge).catch(e=>toast(e.message))};socket.onclose=e=>{$('light').className='';$('connection').textContent='再接続中';if(e.code===1008){disconnect();$('login').showModal();return}if(active)reconnect=setTimeout(connectWS,2500)}}
async function start(){await refresh();active=true;connectWS();clearInterval(timer);timer=setInterval(()=>refresh().catch(e=>toast(e.message)),2500)}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('token').value})});$('token').value='';$('loginError').textContent='';$('login').close();await start()}catch(err){$('loginError').textContent=err.message}};
$('logout').onclick=async()=>{await api('/api/logout',{method:'POST'});disconnect();rows=[];render();$('login').showModal()};
$('toggle').onclick=()=>api(`/api/udp/${enabled?'stop':'start'}`,{method:'POST'}).then(refresh).catch(e=>toast(e.message));
$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'表示を再開':'表示を一時停止';if(!paused)render()};$('source').onchange=render;$('search').oninput=render;window.addEventListener('resize',render);
async function upload(file){if(!file)return;if(file.size>100*1024*1024){toast('最大100 MBです');return}try{await api('/api/files?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await refresh()}catch(e){toast(e.message)}$('file').value=''}
$('file').onchange=e=>upload(e.target.files[0]);$('drop').ondragover=e=>e.preventDefault();$('drop').ondrop=e=>{e.preventDefault();upload(e.dataTransfer.files[0])};initGlobe().catch(e=>toast(e.message));start().catch(e=>{if(e.message!=='ログインが必要です')toast(e.message)});
