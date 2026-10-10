'use strict';
window.CESIUM_BASE_URL = 'cesium/';
function send(body) { window.webkit?.messageHandlers.nmea.postMessage(body); }
window.addEventListener('error', e => send({error: 'GIS: '+e.message}));
const viewer = new Cesium.Viewer('map', {
 baseLayer: Cesium.ImageryLayer.fromProviderAsync(Cesium.TileMapServiceImageryProvider.fromUrl('cesium/Assets/Textures/NaturalEarthII', {credit:'Natural Earth (public domain)'})),
 terrainProvider:new Cesium.EllipsoidTerrainProvider(), animation:false,timeline:false,baseLayerPicker:false,geocoder:false,
 homeButton:true,sceneModePicker:true,navigationHelpButton:false,fullscreenButton:false,infoBox:false,selectionIndicator:true,
 requestRenderMode:true,maximumRenderTimeChange:Infinity
});
viewer.camera.setView({destination:Cesium.Cartesian3.fromDegrees(139.7,35.5,900000)});
let tracks = [];
const standardSelect = document.getElementById('standard');
NmeaSymbols.bind(standardSelect,()=>{});
window.renderTracks = (items, options) => {
 tracks = items;
 if (standardSelect.value !== options.standard) { standardSelect.value=options.standard; standardSelect.dispatchEvent(new Event('change')); }
 viewer.entities.suspendEvents();
 const ids = new Set(items.map(t=>t.mmsi));
 for(const entity of [...viewer.entities.values]) if(!ids.has(entity.id.replace(/^trail:/,''))) viewer.entities.remove(entity);
 for(const t of items) {
  const selected = t.mmsi === options.selected;
  const graphics = NmeaSymbols.graphics({own:t.fields.own==='true',watched:t.watched,selected});
  let e = viewer.entities.getById(t.mmsi);
  if(!e) e = viewer.entities.add({id:t.mmsi});
  e.position=Cesium.Cartesian3.fromDegrees(t.lon,t.lat); e.billboard=graphics.billboard;
  e.label={text:t.fields.shipname||t.mmsi,font:'12px sans-serif',fillColor:Cesium.Color.WHITE,showBackground:true,pixelOffset:new Cesium.Cartesian2(0,28),distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,2000000)};
  const trailId='trail:'+t.mmsi;
  const oldTrail=viewer.entities.getById(trailId); if(oldTrail) viewer.entities.remove(oldTrail);
  if(selected && t.trail.length>1) viewer.entities.add({id:trailId,polyline:{positions:Cesium.Cartesian3.fromDegreesArray(t.trail.flat()),width:2,material:Cesium.Color.CYAN}});
 }
 viewer.entities.resumeEvents();
 viewer.selectedEntity = viewer.entities.getById(options.selected);
 viewer.scene.requestRender();
};
window.focusMmsi = mmsi => { const t=tracks.find(t=>t.mmsi===mmsi); if(t) { viewer.selectedEntity=viewer.entities.getById(mmsi); viewer.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(t.lon,t.lat,45000),duration:0.6}); } };
function picked(position) { const p=viewer.scene.pick(position); const id=p?.id?.id; return typeof id==='string' && !id.startsWith('trail:') ? id : null; }
viewer.screenSpaceEventHandler.setInputAction(e=>{const mmsi=picked(e.position); if(mmsi) send({action:'select',mmsi});},Cesium.ScreenSpaceEventType.LEFT_CLICK);
const menu=document.getElementById('quickMenu');
let menuMmsi;
function showMenu(mmsi,point) {
 menuMmsi=mmsi; document.getElementById('menuTitle').textContent=tracks.find(t=>t.mmsi===mmsi)?.fields.shipname||mmsi;
 menu.hidden=false; menu.style.left=Math.min(point.x,window.innerWidth-200)+'px'; menu.style.top=Math.min(point.y,window.innerHeight-155)+'px';
}
for(const [id,action] of [['menuSelect','select'],['menuWatch','watch']]) document.getElementById(id).addEventListener('click',()=>{send({action,mmsi:menuMmsi});menu.hidden=true;});
document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))menu.hidden=true;});
document.addEventListener('keydown',e=>{if(e.key==='Escape')menu.hidden=true;});
viewer.screenSpaceEventHandler.setInputAction(e=>{const mmsi=picked(e.position); if(mmsi) showMenu(mmsi,e.position);},Cesium.ScreenSpaceEventType.RIGHT_CLICK);
let press,pressStart;
const canvas=viewer.scene.canvas;
canvas.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;const rect=canvas.getBoundingClientRect();const point=new Cesium.Cartesian2(e.clientX-rect.left,e.clientY-rect.top);const mmsi=picked(point); pressStart=point; if(mmsi) press=setTimeout(()=>showMenu(mmsi,point),650);});
for(const event of ['pointerup','pointercancel']) canvas.addEventListener(event,()=>clearTimeout(press));
canvas.addEventListener('pointermove',e=>{const rect=canvas.getBoundingClientRect();if(pressStart&&Math.hypot(e.clientX-rect.left-pressStart.x,e.clientY-rect.top-pressStart.y)>10)clearTimeout(press);});
