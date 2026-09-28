'use strict';
const $=id=>document.getElementById(id);
let rows=[], paused=false, enabled=true, socket=null, timer=null, reconnect=null, active=false;
let globe=null, globeEntities=[], firstFix=true;
let watchList=[],watchAlerts=[],symbolRows=new Map(),identityByMmsi=new Map(),selectedSymbol=null,pendingDuplicate=null;
let focusedMmsi=null,focusedRow=null,focusRequest=0;
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',6500)}
function watchPayload(){return {mmsi:$('watchMmsi').value.trim()||null,imo:$('watchImo').value.trim()||null,
  name:$('watchName').value.trim(),notes:$('watchNotes').value.trim()}}
function watchEditor(item={}){$('watchDialog').dataset.id=item.id||'';$('watchTitle').textContent=item.id?'特定船舶を編集':'特定船舶を登録';
  $('watchMmsi').value=item.mmsi||'';$('watchImo').value=item.imo||'';$('watchName').value=item.name||'';
  $('watchNotes').value=item.notes||'';$('watchError').textContent='';$('watchDialog').showModal()}
function renderWatch(){const body=$('watchRows');body.replaceChildren();$('watchCount').textContent=watchList.length+'件';
  for(const item of watchList){const tr=document.createElement('tr');for(const value of [item.name,item.mmsi||'—',item.imo||'—',item.notes||'—']){
    const cell=document.createElement('td');cell.textContent=value;tr.append(cell)}
    const actions=document.createElement('td'),edit=document.createElement('button'),del=document.createElement('button');
    edit.type=del.type='button';edit.textContent='編集';del.textContent='削除';edit.onclick=()=>watchEditor(item);
    del.onclick=async()=>{if(!confirm(`${item.name}を監視リストから削除しますか？`))return;
      try{await api('/api/watchlist/'+item.id,{method:'DELETE'});await loadWatch()}catch(err){toast(err.message)}};
    actions.append(edit,del);tr.append(actions);body.append(tr)}
  if(!watchList.length)body.innerHTML='<tr><td colspan="5">監視対象は未登録です。</td></tr>';
  if(globe)render()}
async function loadWatch(){watchList=await api('/api/watchlist');renderWatch()}
function renderAlerts(){const area=$('watchAlerts');area.replaceChildren();
  for(const item of watchAlerts.slice(0,15)){const el=document.createElement('button');el.type='button';el.className='watch-alert';
    el.setAttribute('aria-pressed',String(item.mmsi===focusedMmsi));el.title='この船舶を選択して地図の中心に表示';el.onclick=()=>focusAlert(item);
    const time=document.createElement('time');time.textContent=new Date(item.received_at).toLocaleString();
    el.textContent=`検知: ${item.name} / MMSI ${item.mmsi||'—'} / IMO ${item.imo||'—'}（${item.matched_by}一致）`;
    el.append(time);area.append(el)}
  if(!watchAlerts.length)area.textContent='受信アラートはありません。'}
async function focusAlert(item){const request=++focusRequest;
  try{const row=await api('/api/vessels/'+encodeURIComponent(item.mmsi)+'/position');
    if(request!==focusRequest)return;if(!globe){toast('地図の読み込みをお待ちください');return}
    selectTrack(row);firstFix=false;
    draw(filtered());renderAlerts();$('detail').textContent=JSON.stringify(row,null,2);
    $('cesium').scrollIntoView({block:'center',behavior:'instant'});
    globe.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(row.longitude,row.latitude,120000),
      orientation:{heading:0,pitch:-Math.PI/2,roll:0},duration:1});
  }catch(err){if(request===focusRequest)toast(err.message)}}
function addAlerts(items,notify=false){const ids=new Set(watchAlerts.map(a=>a.id));const fresh=items.filter(a=>!ids.has(a.id));
  watchAlerts=[...fresh,...watchAlerts].sort((a,b)=>b.id-a.id).slice(0,100);renderAlerts();
  if(notify&&fresh.length)toast(`監視対象を受信: ${fresh.map(a=>a.name).join('、')}`)}
async function openSymbolWatch(row){$('mapQuickMenu').hidden=true;let item={mmsi:row.mmsi,name:row.decoded?.shipname?.trim(' @')||'MMSI '+row.mmsi};
  try{const identity=await api('/api/identities/'+encodeURIComponent(row.mmsi));item.imo=identity.imo;
    if(identity.shipname)item.name=identity.shipname}catch(err){toast(err.message)}
  watchEditor(item)}
function closeMapQuick(){$('mapQuickMenu').hidden=true}
function mapSymbolAt(screen){const nearby=[...symbolRows].map(([entity,row])=>{
    const p=Cesium.SceneTransforms.worldToWindowCoordinates(globe.scene,entity.position.getValue(globe.clock.currentTime));
    return {row,d:p?Math.hypot(p.x-screen.x,p.y-screen.y):Infinity}}).sort((a,b)=>a.d-b.d);
  if(nearby[0]?.d<=18)return nearby[0].row;
  const picked=globe.scene.pick(screen)?.id;return symbolRows.get(picked)}
function showMapQuick(event){if(!globe)return;const rect=globe.canvas.getBoundingClientRect();
  const row=mapSymbolAt(new Cesium.Cartesian2(event.clientX-rect.left,event.clientY-rect.top));
  if(!row?.mmsi){closeMapQuick();return}selectTrack(row);
  const menu=$('mapQuickMenu');$('mapQuickTitle').textContent='MMSI '+row.mmsi;
  menu.hidden=false;menu.style.left=Math.max(8,Math.min(event.clientX,innerWidth-menu.offsetWidth-8))+'px';
  menu.style.top=Math.max(8,Math.min(event.clientY,innerHeight-menu.offsetHeight-8))+'px';
  $('mapQuickRegister').focus()}
async function api(url,options={}){const r=await fetch(url,options);if(r.status===401){disconnect();if(!$('login').open)$('login').showModal();throw Error('ログインが必要です')}if(!r.ok){let body=await r.json().catch(()=>({}));throw Error(body.detail||`HTTP ${r.status}`)}return r.json()}
function disconnect(){active=false;clearInterval(timer);clearTimeout(reconnect);if(socket){socket.onclose=null;socket.close();socket=null}$('light').className='';$('connection').textContent='未接続'}
function clearDisplay(){clearTrackSelection(false);rows=[];focusedMmsi=null;focusedRow=null;focusRequest++;identityByMmsi.clear();symbolRows.clear();watchAlerts=[];renderAlerts();closeMapQuick();$('rows').replaceChildren();$('detail').textContent='センテンスを選択してください。';$('points').textContent='位置情報を待っています';firstFix=true;if(globe){globe.selectedEntity=undefined;globeEntities.forEach(entity=>globe.entities.remove(entity));globeEntities=[]}}
function merge(data){retainTrackRows(data);const byId=new Map(rows.map(r=>[r.id,r]));for(const r of data){byId.set(r.id,r);
  if(r.mmsi&&r.decoded?.msg_type===5)identityByMmsi.set(r.mmsi,{imo:String(r.decoded.imo||''),shipname:r.decoded.shipname})}
  rows=[...byId.values()].sort((a,b)=>b.id-a.id).slice(0,500);render()}
function filtered(){const search=$('search').value.toLowerCase(), source=$('source').value;return rows.filter(r=>(source==='all'||r.source.startsWith(source+':'))&&(!search||JSON.stringify(r).toLowerCase().includes(search)))}
function render(){if(paused)return;const view=filtered(),body=$('rows');body.replaceChildren();for(const row of view){const tr=document.createElement('tr');tr.dataset.id=row.id;const values=[new Date(row.received_at).toLocaleTimeString(),row.source.startsWith('udp:')?'UDP':(row.filename||'FILE'),row.sentence_type,row.status,row.raw];for(let i=0;i<values.length;i++){const td=document.createElement('td');if(i===3){const badge=document.createElement('span');badge.className='status '+row.status;badge.textContent=({ok:'正常',error:'エラー',pending:'断片待機',unsupported:'未対応'})[row.status]||row.status;td.append(badge)}else{td.textContent=values[i];td.title=String(values[i])}tr.append(td)}tr.onclick=()=>$('detail').textContent=JSON.stringify(row,null,2);body.append(tr)}draw(view)}
function draw(view){
  if(!globe)return;
  globeEntities.forEach(entity=>globe.entities.remove(entity));globeEntities=[];symbolRows.clear();
  const pts=view.filter(r=>r.latitude!==null&&r.longitude!==null);
  if(focusedRow){const latest=trackHistory.find(hasPosition);
    if(latest&&(!focusedRow||latest.id>focusedRow.id))focusedRow=latest;
    if(focusedRow&&!pts.some(r=>r.id===focusedRow.id))pts.unshift(focusedRow)}
  const tracks=new Map();
  for(const row of [...pts].reverse()){
    const key=row.source+':'+(row.mmsi||'GPS');
    if(!tracks.has(key))tracks.set(key,[]);
    tracks.get(key).push(row);
  }
  let index=0;
  for(const [key,list] of tracks){
    const latest=list.at(-1), watched=latest.mmsi&&watchList.some(w=>w.mmsi===latest.mmsi||w.imo&&w.imo===identityByMmsi.get(latest.mmsi)?.imo);
    const color=watched?Cesium.Color.RED:[Cesium.Color.TURQUOISE,Cesium.Color.CORNFLOWERBLUE,Cesium.Color.ORANGE,Cesium.Color.VIOLET][index++%4];
    const coords=list.map(p=>Cesium.Cartesian3.fromDegrees(p.longitude,p.latitude));
    if(coords.length>1)globeEntities.push(globe.entities.add({polyline:{positions:coords,width:2,material:color.withAlpha(.75)}}));
    const cog=Number(latest.decoded?.course??latest.decoded?.cog??latest.decoded?.true_course);
    const lon=latest.longitude,lat=latest.latitude;
    const description='MMSI '+(latest.mmsi||'自船')+' / '+latest.received_at;
    const symbol=globe.entities.add({name:latest.mmsi||'GPS',description,
      position:Cesium.Cartesian3.fromDegrees(lon,lat),
      ...NmeaSymbols.graphics({own:!latest.mmsi,watched,selected:latest.mmsi===focusedMmsi&&latest.id===focusedRow?.id}),
      label:{text:latest.mmsi||'GPS',font:'12px sans-serif',fillColor:Cesium.Color.WHITE,showBackground:true,
             pixelOffset:new Cesium.Cartesian2(0,-34),distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,3000000)}});
    globeEntities.push(symbol);symbolRows.set(symbol,latest);
    if(latest.mmsi===focusedMmsi&&latest.id===focusedRow?.id){globe.selectedEntity=symbol;selectedSymbol=latest}
    if(Number.isFinite(cog) && cog>=0 && cog<360){
      const d=.012,r=cog*Math.PI/180, nextLat=lat+d*Math.cos(r),nextLon=lon+d*Math.sin(r)/Math.max(.1,Math.cos(lat*Math.PI/180));
      globeEntities.push(globe.entities.add({polyline:{positions:Cesium.Cartesian3.fromDegreesArray([lon,lat,nextLon,nextLat]),width:2,material:color}}));
    }
  }
  renderTrackDetails();
  $('points').textContent=`${pts.length} ポイント / ${tracks.size} トラック`;
  if(firstFix&&pts.length){firstFix=false;const p=pts[0];globe.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(p.longitude,p.latitude,350000),duration:1.3})}
}
async function initGlobe(){
  if(!window.Cesium){toast('Cesiumの読み込みに失敗しました');return}
  globe=new Cesium.Viewer('cesium',{baseLayer:false,baseLayerPicker:false,geocoder:false,homeButton:true,
    infoBox:false,navigationHelpButton:false,animation:false,timeline:false,sceneModePicker:true,terrainProvider:new Cesium.EllipsoidTerrainProvider()});
  globe.scene.globe.baseColor=Cesium.Color.fromCssColorString('#193349');
  globe.camera.setView({destination:Cesium.Cartesian3.fromDegrees(139.75,35.65,3000000)});
  document.addEventListener('contextmenu',event=>{if($('cesium').contains(event.target))event.preventDefault()},true);
  document.addEventListener('pointerup',event=>{if(event.button===2&&$('cesium').contains(event.target))showMapQuick(event)},true);
  document.addEventListener('pointerdown',event=>{if(!$('mapQuickMenu').contains(event.target))closeMapQuick()});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeMapQuick()});
  globe.screenSpaceEventHandler.setInputAction(event=>{const row=mapSymbolAt(event.position);
    if(row)selectTrack(row);else clearTrackSelection();closeMapQuick()},Cesium.ScreenSpaceEventType.LEFT_CLICK);
  try {
    const imagery=await Cesium.TileMapServiceImageryProvider.fromUrl(Cesium.buildModuleUrl('Assets/Textures/NaturalEarthII'));
    globe.imageryLayers.addImageryProvider(imagery);
  }catch(error){toast('地球の背景図を読み込めませんでした: '+error.message)}
  render();
}

async function refresh(){const [s,jobs]=await Promise.all([api('/api/stats'),api('/api/jobs')]);$('total').textContent=s.total.toLocaleString();$('success').textContent=(s.statuses.ok||0).toLocaleString();$('errors').textContent=(s.statuses.error||0).toLocaleString();$('datagrams').textContent=s.runtime.datagrams.toLocaleString();enabled=s.udp_enabled;$('toggle').textContent=enabled?'受信停止':'受信再開';$('udpStatus').textContent=`UDP ${s.udp_port} / TCP ${s.tcp_port} · ${enabled?'受信中':'停止中'} · TCP接続 ${s.runtime.tcp_connections}`;$('queue').textContent=`待機 ${s.queue_size} / AIS未完了 ${s.ais_pending}`;$('warning').textContent=`キュー破棄 ${s.runtime.queue_dropped} · DB保存失敗 ${s.runtime.db_errors} · AISタイムアウト ${s.ais_expired} · 配信破棄 ${s.runtime.ws_dropped}`;$('jobs').replaceChildren();for(const j of jobs.slice(0,8)){const el=document.createElement('div');el.className='job';const title=document.createElement('span');title.textContent=j.filename;el.append(title);if(['running','queued'].includes(j.status)){const b=document.createElement('button');b.textContent='停止';b.onclick=()=>api(`/api/jobs/${j.id}/cancel`,{method:'POST'}).catch(e=>toast(e.message));el.append(b)}const p=document.createElement('progress');p.max=Math.max(j.size,1);p.value=j.bytes_read;el.append(p);const sm=document.createElement('small');sm.textContent=`${j.status} · ${j.lines}行 · 正常 ${j.ok} / エラー ${j.error} / 未完了AIS ${j.incomplete_ais_groups||0}`;el.append(sm);$('jobs').append(el)}}
function connectWS(){if(!active)return;socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/ws`);socket.onopen=()=>{$('light').className='live';$('connection').textContent='LIVE / 接続中';api('/api/events?limit=500').then(merge).catch(e=>toast(e.message));api('/api/watch-alerts').then(items=>addAlerts(items)).catch(e=>toast(e.message))};socket.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.type==='events'){merge(msg.rows);addAlerts(msg.alerts||[],true)}if(msg.type==='reset'){clearDisplay();refresh().catch(e=>toast(e.message))}if(msg.type==='gap'){api('/api/events?limit=500').then(merge).catch(e=>toast(e.message));api('/api/watch-alerts').then(items=>addAlerts(items)).catch(e=>toast(e.message))}};socket.onclose=e=>{$('light').className='';$('connection').textContent='再接続中';if(e.code===1008){disconnect();$('login').showModal();return}if(active)reconnect=setTimeout(connectWS,2500)}}
async function start(){await Promise.all([refresh(),loadWatch(),api('/api/watch-alerts').then(items=>addAlerts(items))]);active=true;connectWS();clearInterval(timer);timer=setInterval(()=>refresh().catch(e=>toast(e.message)),2500)}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:$('token').value})});$('token').value='';$('loginError').textContent='';$('login').close();await start()}catch(err){$('loginError').textContent=err.message}};
$('logout').onclick=async()=>{await api('/api/logout',{method:'POST'});disconnect();clearDisplay();render();$('login').showModal()};
NmeaSymbols.bind($('symbolStandard'),()=>draw(filtered()));
$('trackClose').onclick=()=>clearTrackSelection();
$('watchAdd').onclick=()=>watchEditor();$('watchCancel').onclick=()=>$('watchDialog').close();
$('mapQuickRegister').onclick=()=>{if(selectedSymbol)openSymbolWatch(selectedSymbol)};
$('mapQuickCenter').onclick=()=>{if(selectedSymbol)globe.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(selectedSymbol.longitude,selectedSymbol.latitude,120000)});closeMapQuick()};
$('watchForm').onsubmit=async event=>{event.preventDefault();const data=watchPayload();if(!data.mmsi&&!data.imo){$('watchError').textContent='MMSIまたはIMO番号を入力してください';return}
  const id=$('watchDialog').dataset.id;const url=id?'/api/watchlist/'+id:'/api/watchlist';
  try{const response=await fetch(url,{method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    if(response.status===409){const conflict=await response.json();$('watchDialog').close();pendingDuplicate={data,existing:conflict.existing};
      $('duplicateInfo').textContent=conflict.existing.length===1?`登録済み: ${conflict.existing[0].name}（MMSI ${conflict.existing[0].mmsi||'—'} / IMO ${conflict.existing[0].imo||'—'}）`:'複数の登録に重複します。一覧から登録内容を整理してください。';
      $('duplicateUpdate').disabled=conflict.existing.length!==1;$('duplicateDialog').showModal();return}
    if(!response.ok)throw Error((await response.json()).detail||'保存に失敗しました');
    $('watchDialog').close();await loadWatch();toast('監視リストを保存しました')}
  catch(err){$('watchError').textContent=err.message}};
$('duplicateCancel').onclick=()=>{$('duplicateDialog').close();pendingDuplicate=null};
$('duplicateUpdate').onclick=async()=>{if(!pendingDuplicate||pendingDuplicate.existing.length!==1)return;
  try{await api('/api/watchlist/'+pendingDuplicate.existing[0].id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(pendingDuplicate.data)});
    $('duplicateDialog').close();pendingDuplicate=null;await loadWatch();toast('登録済みの船舶を更新しました')}
  catch(err){$('duplicateInfo').textContent=err.message}};
$('toggle').onclick=()=>api(`/api/udp/${enabled?'stop':'start'}`,{method:'POST'}).then(refresh).catch(e=>toast(e.message));
$('deleteData').onclick=async()=>{try{const stats=await api('/api/stats');$('deleteCount').textContent=`現在の保存件数: ${stats.total.toLocaleString()} 件`; $('deleteDialog').dataset.total=stats.total;$('deleteConfirm').value='';$('deleteError').textContent='';$('deleteExecute').disabled=true;$('deleteDialog').showModal()}catch(e){toast(e.message)}};
$('deleteCancel').onclick=()=>$('deleteDialog').close();
$('deleteConfirm').oninput=()=>$('deleteExecute').disabled=$('deleteConfirm').value!=='全件削除';
$('deleteForm').onsubmit=async event=>{event.preventDefault();if($('deleteConfirm').value!=='全件削除')return;$('deleteExecute').disabled=true;
  try{const result=await api('/api/data',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:$('deleteConfirm').value,expected_total:Number($('deleteDialog').dataset.total)})});$('deleteDialog').close();clearDisplay();await refresh();toast(`${result.events_deleted}件の履歴と${result.jobs_deleted}件のジョブを削除しました。受信は停止中です。`)}
  catch(e){$('deleteError').textContent=e.message;$('deleteExecute').disabled=false}};
$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'表示を再開':'表示を一時停止';if(!paused)render()};$('source').onchange=render;$('search').oninput=render;window.addEventListener('resize',render);
async function upload(file){if(!file)return;if(file.size>100*1024*1024){toast('最大100 MBです');return}try{await api('/api/files?filename='+encodeURIComponent(file.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});await refresh()}catch(e){toast(e.message)}$('file').value=''}
$('file').onchange=e=>upload(e.target.files[0]);$('drop').ondragover=e=>e.preventDefault();$('drop').ondrop=e=>{e.preventDefault();upload(e.dataTransfer.files[0])};initGlobe().catch(e=>toast(e.message));start().catch(e=>{if(e.message!=='ログインが必要です')toast(e.message)});
