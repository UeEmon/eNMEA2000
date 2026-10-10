// Run with bundled assets served at http://127.0.0.1:18082.
const {chromium}=require('../../browser-tests/node_modules/playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 try {
  const page=await browser.newPage({viewport:{width:1366,height:1024}});
  const errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{const u=new URL(route.request().url());if(u.protocol==='http:'&&u.hostname==='127.0.0.1')return route.continue();if(['blob:','data:'].includes(u.protocol))return route.continue();external.push(u.href);return route.abort();});
  await page.addInitScript(()=>{window.messages=[];window.webkit={messageHandlers:{nmea:{postMessage:body=>window.messages.push(body)}}};});
  await page.goto('http://127.0.0.1:18082/index.html',{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForFunction(()=>typeof window.renderTracks==='function',{},{timeout:60000}).catch(e=>{throw Error(e.message+' '+JSON.stringify({errors,external}));});
  const tracks=[{mmsi:'123456789',lat:35.5,lon:139.7,fields:{shipname:'TEST',own:'false'},watched:true,trail:[[139.69,35.49],[139.7,35.5]]}];
  for(const standard of ['2525','APP6']) {
   await page.evaluate(({tracks,standard})=>{window.renderTracks(tracks,{selected:'123456789',standard});window.focusMmsi('123456789');},{tracks,standard});
   await page.waitForTimeout(1000);
   const state=await page.evaluate(()=>({count:viewer.entities.values.length,selected:viewer.selectedEntity?.id,standard:NmeaSymbols.getStandard(),image:viewer.entities.getById('123456789').billboard.image.getValue() instanceof HTMLCanvasElement}));
   if(state.count!==2||state.selected!=='123456789'||state.standard!==standard||!state.image)throw Error(JSON.stringify(state));
  }
  const point=await page.evaluate(()=>{const e=viewer.entities.getById('123456789'),p=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,e.position.getValue(viewer.clock.currentTime));return {x:p.x,y:p.y};});
  await page.mouse.click(point.x,point.y,{button:'right'});
  await page.getByRole('menuitem',{name:'監視対象に登録'}).click();
  await page.waitForFunction(()=>window.messages.some(m=>m.action==='watch'&&m.mmsi==='123456789'));
  // Own position remains at the GIS center even when selecting/focusing another target.
  for(const standard of ['2525','APP6']) for(const ownPlatform of ['ship','aircraft']) {
   await page.evaluate(({tracks,standard,ownPlatform})=>window.renderTracks(tracks,{selected:'123456789',standard,ownPlatform,followOwn:true,own:{lat:35.4,lon:139.6,kind:'VDO'}}),{tracks,standard,ownPlatform});
   await page.waitForTimeout(500);
   const state=await page.evaluate(()=>{
    const own=viewer.entities.getById('__own__'),p=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,own.position.getValue(viewer.clock.currentTime));
    return {tracked:viewer.trackedEntity?.id,selected:viewer.selectedEntity?.id,x:p.x,y:p.y,w:viewer.canvas.clientWidth,h:viewer.canvas.clientHeight,code:NmeaSymbols.sidc(true,false,'aircraft'),image:own.billboard.image.getValue().toDataURL()};
   });
   if(state.tracked!=='__own__'||state.selected!=='123456789'||Math.abs(state.x-state.w/2)>3||Math.abs(state.y-state.h/2)>3)throw Error('Own center: '+JSON.stringify(state));
   await page.evaluate(()=>window.focusMmsi('123456789'));
   if(await page.evaluate(()=>viewer.trackedEntity?.id)!=='__own__')throw Error('Target selection lost own tracking');
   await page.evaluate(({tracks,standard,ownPlatform})=>window.renderTracks(tracks,{selected:'123456789',standard,ownPlatform,followOwn:true,own:{lat:35.45,lon:139.65,kind:'RMC'}}),{tracks,standard,ownPlatform});
   await page.waitForTimeout(500);
   const centered=await page.evaluate(()=>{const own=viewer.entities.getById('__own__'),p=Cesium.SceneTransforms.worldToWindowCoordinates(viewer.scene,own.position.getValue(viewer.clock.currentTime));return Math.abs(p.x-viewer.canvas.clientWidth/2)<3&&Math.abs(p.y-viewer.canvas.clientHeight/2)<3});
   if(!centered)throw Error('Updated own position not centered');
  }
  const images=await page.evaluate(()=>['ship','aircraft'].map(platform=>NmeaSymbols.graphics({own:true,platform}).billboard.image.toDataURL()));
  if(images[0]===images[1])throw Error('Ship and aircraft symbols must differ');
  await page.evaluate(({tracks})=>window.renderTracks(tracks,{selected:'123456789',standard:'2525',ownPlatform:'ship',followOwn:false,own:{lat:35.45,lon:139.65}}),{tracks});
  if(await page.evaluate(()=>Boolean(viewer.trackedEntity)||!viewer.scene.screenSpaceCameraController.enableTranslate))throw Error('Follow off must release the map');
  await page.evaluate(({tracks})=>window.renderTracks(tracks,{selected:'123456789',standard:'2525',followOwn:true}),{tracks});
  if(await page.evaluate(()=>Boolean(viewer.trackedEntity)||Boolean(viewer.entities.getById('__own__'))))throw Error('No fix must not produce own symbol');
  await page.screenshot({path:'/tmp/enmea-ipad-map.png'});
  if(errors.length||external.length)throw Error(JSON.stringify({errors,external}));
  console.log('PASS: offline Cesium + both symbol standards + selection/trail + watch registration + own ship/aircraft + moving center lock on/off');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
