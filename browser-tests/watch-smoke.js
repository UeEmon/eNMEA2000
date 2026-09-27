const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const net=require('node:net');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token);
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const page=await browser.newPage({viewport:{width:1500,height:1000}});
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto('http://127.0.0.1:18081');
    await page.locator('#token').fill(token);
    await page.getByRole('button',{name:'接続する'}).click();
    await page.getByRole('button',{name:'MMSI / IMOを登録'}).click();
    await page.locator('#watchImo').fill('1234567');
    await page.locator('#watchName').fill('監視船');
    await page.getByRole('dialog',{name:'特定船舶を登録'}).getByRole('button',{name:'保存する'}).click();
    await page.waitForFunction(()=>document.querySelector('#watchCount')?.textContent==='1件');
    const frames=execFileSync('docker',['compose','exec','-T','app','python','-c',"from pyais.encode import encode_dict; print('\\n'.join(encode_dict({'msg_type':5,'mmsi':431888777,'imo':1234567,'shipname':'WATCH SHIP'},talker_id='AI')+encode_dict({'msg_type':1,'mmsi':431888777,'lat':35.65,'lon':139.75,'speed':1,'course':90},talker_id='AI')))"]).toString();
    await new Promise((resolve,reject)=>{const sock=net.connect(10111,'127.0.0.1',()=>sock.end(frames));sock.on('end',resolve);sock.on('error',reject)});
    await page.waitForFunction(()=>document.querySelector('#watchAlerts')?.textContent?.includes('監視船'),{timeout:15000});
    await page.waitForFunction(()=>[...symbolRows.values()].some(row=>row.mmsi==='431888777'),{timeout:15000});
    await page.waitForTimeout(1500);
    const point=await page.evaluate(()=>{const entry=[...symbolRows].find(([_,row])=>row.mmsi==='431888777');
      const p=Cesium.SceneTransforms.worldToWindowCoordinates(globe.scene,entry[0].position.getValue(globe.clock.currentTime));
      const b=globe.canvas.getBoundingClientRect();return {x:b.left+p.x,y:b.top+p.y}});
    await page.mouse.click(point.x,point.y,{button:'right'});
    await page.getByRole('menuitem',{name:'この船舶を監視リストに登録'}).click();
    await page.getByRole('dialog',{name:'特定船舶を登録'}).getByRole('button',{name:'保存する'}).click();
    await page.getByRole('dialog',{name:'登録済みの船舶です'}).getByRole('button',{name:'更新する'}).click();
    await page.waitForFunction(()=>document.querySelector('#watchCount')?.textContent==='1件' && document.querySelector('#watchRows')?.textContent?.includes('431888777'));
    assert.deepEqual(errors,[]);
    console.log('PASS: IMO watch alert, GIS right-click registration, duplicate update');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
