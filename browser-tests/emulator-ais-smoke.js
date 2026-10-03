const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');

(async()=>{
  const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token);
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const context=await browser.newContext({viewport:{width:1500,height:1000}});
    const app=await context.newPage();
    await app.goto('http://127.0.0.1:18081');
    await app.locator('#token').fill(token);
    await app.getByRole('button',{name:'接続する'}).click();
    await app.waitForFunction(()=>active&&globe);
    const before=(await (await app.request.get('http://127.0.0.1:18081/api/events?limit=1')).json())[0]?.id||0;
    const page=await context.newPage();
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:8090',{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelectorAll('#aisScenario option').length===42);
    const catalog=await (await page.request.get('http://127.0.0.1:8090/api/ais/scenarios')).json();
    assert.deepEqual(catalog.types,Array.from({length:29},(_,i)=>i));
    assert.equal(catalog.scenarios.length,42);
    await page.locator('#aisScenario').selectOption('type-5');
    assert((await page.locator('#suiteFrames').textContent()).split('\n').length===2);
    await page.locator('#sendAllScenarios').click();
    await page.waitForFunction(()=>document.querySelector('#suiteResult').textContent.includes('42項目 / 45文'),null,{timeout:15000});
    const deadline=Date.now()+20000;
    let received=[];
    while(Date.now()<deadline){
      const response=await app.request.get('http://127.0.0.1:18081/api/events?limit=300&after='+before);
      assert(response.ok());
      const rows=await response.json();
      const marker=rows.find(row=>row.raw===catalog.scenarios[0].frames[0]&&row.source.startsWith('tcp:'));
      if(marker){received=rows.filter(row=>row.source===marker.source);if(received.length>=45)break}
      await page.waitForTimeout(150);
    }
    assert.equal(received.length,45);
    assert.deepEqual([...new Set(received.filter(row=>row.status==='ok').map(row=>row.ais_type))].sort((a,b)=>a-b),catalog.types);
    assert.equal(received.filter(row=>row.status==='pending').length,3);
    assert.deepEqual(errors,[]);
    console.log('PASS: emulator UI sent all 42 AIS scenarios over TCP; all 29 types persisted');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
