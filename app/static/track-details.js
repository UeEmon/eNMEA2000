'use strict';
let trackHistory=[],trackIdentity={},trackRequest=0,trackLoadMessage='';
function sameTrack(row){return focusedRow&&(focusedRow.mmsi?row.mmsi===focusedRow.mmsi:!row.mmsi&&row.source===focusedRow.source)}
function hasPosition(row){return row.status==='ok'&&Number.isFinite(row.latitude)&&Number.isFinite(row.longitude)}
function retainTrackRows(data){
  if(!focusedRow)return;
  const byId=new Map(trackHistory.map(row=>[row.id,row]));
  for(const row of data)if(sameTrack(row))byId.set(row.id,row);
  trackHistory=[...byId.values()].sort((a,b)=>b.id-a.id).slice(0,500);
}
function selectTrack(row){
  focusedMmsi=row.mmsi;focusedRow=row;selectedSymbol=row;focusRequest++;
  trackHistory=[];trackIdentity={};trackLoadMessage='保存済みの航跡情報を読み込み中…';
  retainTrackRows([row,...rows]);draw(filtered());renderAlerts();
  $('detail').textContent=JSON.stringify(row,null,2);
  const request=++trackRequest;
  const query=new URLSearchParams({limit:'500',...(row.mmsi?{mmsi:row.mmsi}:{source:row.source})});
  Promise.all([api('/api/events?'+query),row.mmsi?api('/api/identities/'+encodeURIComponent(row.mmsi)):Promise.resolve({})])
    .then(([history,identity])=>{if(request!==trackRequest)return;trackIdentity=identity;retainTrackRows(history);trackLoadMessage='';draw(filtered())})
    .catch(err=>{if(request!==trackRequest)return;trackLoadMessage='履歴取得失敗: '+err.message;renderTrackDetails()});
}
function clearTrackSelection(redraw=true){
  trackRequest++;focusRequest++;focusedMmsi=null;focusedRow=null;selectedSymbol=null;
  trackHistory=[];trackIdentity={};trackLoadMessage='';
  if(globe)globe.selectedEntity=undefined;
  renderTrackDetails();renderAlerts();closeMapQuick();if(redraw)draw(filtered());
}
function trackNumber(value,unit='',max=Infinity,digits=1){
  if(value===null||value===undefined||value==='')return '—';
  const n=Number(value);return Number.isFinite(n)&&n>=0&&n<max?n.toFixed(digits)+unit:'—';
}
function renderTrackDetails(){
  const row=focusedRow;
  $('trackEmpty').hidden=!!row;$('trackContent').hidden=!row;$('trackClose').disabled=!row;
  if(!row){$('trackFields').replaceChildren();$('trackHistory').replaceChildren();$('trackRaw').textContent='';$('trackName').textContent='';$('trackStatus').textContent='';return}
  const d=row.decoded||{},positions=trackHistory.filter(hasPosition);
  const identity={...trackIdentity,...identityByMmsi.get(row.mmsi)};
  const name=identity.shipname||trackHistory.find(r=>r.decoded?.shipname)?.decoded.shipname;
  const imo=identity.imo||trackHistory.find(r=>r.decoded?.imo)?.decoded.imo;
  const watched=watchList.some(w=>w.mmsi&&w.mmsi===row.mmsi||w.imo&&w.imo===String(imo));
  $('trackName').textContent=name|| (row.mmsi?'MMSI '+row.mmsi:'自船 GPS');
  const fields=[['MMSI',row.mmsi||'—'],['IMO',imo||'—'],['監視対象',watched?'登録済み':'未登録'],
    ['最新受信時刻',new Date(row.received_at).toLocaleString()],['入力元',row.source],
    ['緯度',row.latitude.toFixed(6)+'°'],['経度',row.longitude.toFixed(6)+'°'],
    ['対地針路（COG）',trackNumber(d.course??d.cog??d.true_course,'°',360)],
    ['対地速力（SOG）',trackNumber(d.speed??d.spd_over_grnd,' kn',row.mmsi?102.3:Infinity)],
    ['船首方位',trackNumber(d.heading,'°',360,0)],['メッセージ',d.msg_type!==undefined?'AIS Type '+d.msg_type+(row.ais_type_name?' / '+row.ais_type_name:''):row.sentence_type]];
  const list=$('trackFields');list.replaceChildren();
  for(const [label,value] of fields){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=label;dd.textContent=String(value);list.append(dt,dd)}
  $('trackStatus').textContent=trackLoadMessage||`取得済み最新500件以内の位置情報 ${positions.length}件（下表は最新20件・受信順）`;
  const body=$('trackHistory');body.replaceChildren();
  for(const p of positions.slice(0,20)){const tr=document.createElement('tr');
    for(const value of [new Date(p.received_at).toLocaleString(),p.latitude.toFixed(5),p.longitude.toFixed(5)]){const td=document.createElement('td');td.textContent=value;tr.append(td)}body.append(tr)}
  $('trackRaw').textContent=JSON.stringify(row,null,2);
}
