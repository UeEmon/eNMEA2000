/* Shared offline AIS symbology. SIDC: v10, reality/simulation, identity, sea surface. */
'use strict';
window.NmeaSymbols=(()=>{
  const key='nmea.symbolStandard',cache=new Map();
  let standard='2525';
  try{if(localStorage.getItem(key)==='APP6')standard='APP6'}catch(_){/* Storage may be disabled. */}
  function sidc(own=false,simulation=false,platform='ship'){return '10'+(simulation?'2':'0')+(own?'3':'1')+(platform==='aircraft'?'0100001101000000':'3000000000000000')}
  function graphics({own=false,simulation=false,watched=false,selected=false,platform='ship'}={}){
    const code=sidc(own,simulation,platform),id=[standard,code,watched,selected].join(':');
    let asset=cache.get(id);
    if(!asset){
      ms.setStandard(standard);
      const symbol=new ms.Symbol(code,{size:28,outlineWidth:selected?4:watched?3:1,
        outlineColor:selected?'#ffd36d':watched?'#ff754c':'#112233'});
      if(!symbol.isValid())throw Error('Invalid AIS symbol: '+code);
      const size=symbol.getSize(),anchor=symbol.getAnchor();
      asset={canvas:symbol.asCanvas(2),size,anchor};cache.set(id,asset);
    }
    return {billboard:{image:asset.canvas,width:asset.size.width,height:asset.size.height,
      horizontalOrigin:Cesium.HorizontalOrigin.CENTER,verticalOrigin:Cesium.VerticalOrigin.CENTER,
      pixelOffset:new Cesium.Cartesian2(asset.size.width/2-asset.anchor.x,asset.size.height/2-asset.anchor.y),
      heightReference:Cesium.HeightReference.CLAMP_TO_GROUND}};
  }
  function bind(select,onChange){select.value=standard;select.addEventListener('change',()=>{
    standard=select.value==='APP6'?'APP6':'2525';
    try{localStorage.setItem(key,standard)}catch(_){}
    onChange();
  })}
  return {graphics,bind,sidc,getStandard:()=>standard};
})();
