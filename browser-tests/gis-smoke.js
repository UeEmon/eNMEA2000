const { chromium }=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
 try{
   const page=await browser.newPage({viewport:{width:1500,height:1000}});
   const errors=[];page.on('pageerror',err=>errors.push(err.message));
   await page.goto('http://127.0.0.1:8090',{waitUntil:'networkidle'});
   await page.waitForSelector('#map canvas',{timeout:30000});
   const canvas=page.locator('#map canvas').first(),box=await canvas.boundingBox();
   if(!box||box.width<300)throw Error('Cesium canvas not visible');
   const status=async()=>page.evaluate(()=>fetch('/api/status').then(r=>r.json()));
   await page.locator('[data-mode="waypoint"]').click();
   await page.mouse.click(box.x+box.width*.53,box.y+box.height*.48);
   await page.waitForFunction(async()=>{const s=await fetch('/api/status').then(r=>r.json());return s.config.route.waypoints.length===1},{timeout:10000});
   const route=await status();
   await page.locator('[data-mode="position"]').click();
   await page.mouse.click(box.x+box.width*.45,box.y+box.height*.54);
   await page.waitForFunction(async()=>{const s=await fetch('/api/status').then(r=>r.json());return Math.abs(s.position.lat-35.65)>0.001||Math.abs(s.position.lon-139.75)>0.001},{timeout:10000});
   const moved=await status();
   await page.getByRole('tab',{name:'GGA'}).click();
   if(await page.getByRole('tabpanel',{name:'GGA'}).isVisible()!==true)throw Error('GGA panel hidden');
   await page.locator('#gga').uncheck();
   await page.getByRole('tab',{name:'RMC'}).click();
   await page.locator('#rmc').uncheck();
   await page.getByRole('tab',{name:'AIS 5'}).click();
   await page.locator('#ais_type5').uncheck();
   await page.getByRole('tab',{name:'AIS 1'}).click();
   await page.getByRole('tab',{name:'AIS 1'}).press('ArrowLeft');
   if(await page.getByRole('tab',{name:'GGA'}).getAttribute('aria-selected')!=='true')throw Error('Keyboard tab navigation failed');
   await page.getByRole('button',{name:'送信開始・設定反映'}).click();
   await page.waitForFunction(async()=>{const c=(await fetch('/api/status').then(r=>r.json())).config;return !c.rmc&&!c.gga&&!c.ais_type5&&c.ais_type1},{timeout:10000});
   if(errors.length)throw Error(errors.join('\n'));
   console.log('PASS: Cesium map actions and per-message tab settings',route.config.route.waypoints[0],moved.position);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
