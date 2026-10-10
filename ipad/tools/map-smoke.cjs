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
  await page.goto('http://127.0.0.1:18082/index.html');
  await page.waitForFunction(()=>typeof window.renderTracks==='function');
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
  await page.screenshot({path:'/tmp/enmea-ipad-map.png'});
  if(errors.length||external.length)throw Error(JSON.stringify({errors,external}));
  console.log('PASS: offline Cesium + both symbol standards + selection/trail + watch registration');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
