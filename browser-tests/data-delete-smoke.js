const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  // This CI script only runs against ephemeral Compose volumes.
  await fetch('http://127.0.0.1:8090/api/stop',{method:'POST'});
  const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token,'APP_TOKEN missing');
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto('http://127.0.0.1:18081');
    await page.locator('#token').fill(token);
    await page.getByRole('button',{name:'接続する'}).click();
    await page.waitForFunction(()=>document.querySelector('#total')?.textContent?.match(/[0-9]/));
    await page.getByRole('button',{name:'保存データ削除'}).click();
    await page.locator('#deleteConfirm').fill('wrong');
    assert(await page.locator('#deleteExecute').isEnabled()===false);
    await page.locator('#deleteConfirm').fill('全件削除');
    await page.getByRole('button',{name:'削除する'}).click();
    await page.waitForFunction(()=>!document.querySelector('#deleteDialog').open && document.querySelector('#total').textContent==='0');
    const stats=await page.evaluate(()=>fetch('/api/stats').then(r=>r.json()));
    assert.equal(stats.total,0);assert.equal(stats.udp_enabled,false);
    assert.equal((await page.evaluate(()=>fetch('/api/jobs').then(r=>r.json()))).length,0);
    assert.deepEqual(errors,[]);
    console.log('PASS: authenticated database deletion confirmation, zero events/jobs, receiving paused');
  }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
