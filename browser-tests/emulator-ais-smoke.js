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
    await page.locator('#suiteLat').fill('34.5');
    await page.locator('#suiteLon').fill('135.5');
    await page.locator('#suiteSpacing').fill('2');
    const [startedResponse]=await Promise.all([
      page.waitForResponse(response=>response.url().endsWith('/api/ais/motion/start')&&response.request().method()==='POST'),
      page.locator('#sendAllScenarios').click()
    ]);
    assert(startedResponse.ok());const initial=await startedResponse.json();assert(initial.active);
    await page.waitForFunction(()=>document.querySelector('#suiteResult').textContent.includes('42項目 / 87文'),null,{timeout:15000});
    assert.equal(await page.evaluate(()=>viewer.entities.values.filter(item=>item.id.startsWith('sim-suite-type-')).length),42);
    const markers=initial.markers;
    assert.deepEqual([1,2,3].map(ring=>markers.filter(item=>item.ring===ring).length),[7,14,21]);
    const deadline=Date.now()+20000;
    let received=[];
    while(Date.now()<deadline){
      const response=await app.request.get('http://127.0.0.1:18081/api/events?limit=300&after='+before);
      assert(response.ok());
      const rows=await response.json();
      const marker=rows.find(row=>row.ais_type===0&&row.mmsi===String(markers[0].mmsi)&&row.source.startsWith('tcp:'));
      if(marker){received=rows.filter(row=>row.source===marker.source);if(received.length>=87)break}
      await page.waitForTimeout(150);
    }
    assert.equal(received.length,87);
    assert.deepEqual([...new Set(received.filter(row=>row.status==='ok').map(row=>row.ais_type))].sort((a,b)=>a-b),catalog.types);
    assert.equal(received.filter(row=>row.status==='pending').length,3);
    for(const marker of markers){const position=received.findLast(row=>row.ais_type===1&&row.mmsi===String(marker.mmsi));
      assert(position,marker.id);assert(Math.abs(position.latitude-marker.lat)<.00001);assert(Math.abs(position.longitude-marker.lon)<.00001)}
    let motion;
    const motionDeadline=Date.now()+15000;
    while(Date.now()<motionDeadline){
      motion=await (await page.request.get('http://127.0.0.1:8090/api/ais/motion')).json();
      if(motion.active&&motion.cycles>=2)break;
      await page.waitForTimeout(150);
    }
    assert(motion.active&&motion.cycles>=2);
    assert(motion.interval>=1&&motion.angular_step_deg>0);
    assert.notEqual(motion.markers[0].lon,markers[0].lon);
    await page.waitForFunction(()=>suiteMarkers.length===42&&suiteMarkers[0].angle>0);
    assert(await page.locator('#suiteLat').isDisabled());
    const motionRows=await (await app.request.get('http://127.0.0.1:18081/api/events?limit=500&after='+before)).json();
    assert(motionRows.some(row=>row.ais_type===1&&row.mmsi===String(markers[0].mmsi)&&row.decoded.speed>0));
    await page.locator('#stopRingMotion').click();
    await page.waitForFunction(()=>!document.querySelector('#suiteLat').disabled);
    const stopped=await (await page.request.get('http://127.0.0.1:8090/api/ais/motion')).json();
    assert(!stopped.active&&!stopped.connected);
    const stoppedSender=await (await page.request.get('http://127.0.0.1:8090/api/status')).json();
    assert(!stoppedSender.active&&!stoppedSender.connected);
    await page.waitForTimeout(1300);
    const afterStop=await (await page.request.get('http://127.0.0.1:8090/api/ais/motion')).json();
    assert.equal(afterStop.cycles,stopped.cycles);
    const afterSender=await (await page.request.get('http://127.0.0.1:8090/api/status')).json();
    assert.equal(afterSender.lines,stoppedSender.lines);
    assert.deepEqual(errors,[]);
    console.log('PASS: 42 AIS scenarios, three concentric rings, automatic TCP motion and stop');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
