const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const net=require('node:net');
const dgram=require('node:dgram');

(async()=>{
  const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token);
  const payload=fs.readFileSync('samples/ais-all-types.log');
  const frames=payload.toString().trim().split(/\r?\n/);
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const page=await browser.newPage({baseURL:'http://127.0.0.1:18081',viewport:{width:1500,height:1000}});
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto('http://127.0.0.1:18081');
    await page.locator('#token').fill(token);
    await page.getByRole('button',{name:'接続する'}).click();
    await page.waitForFunction(()=>active&&globe);
    function validate(rows){
      assert.equal(rows.length,frames.length);
      assert.equal(rows.filter(row=>row.status==='pending').length,1);
      const good=rows.filter(row=>row.status==='ok');
      assert.equal(good.length,31);
      assert.deepEqual([...new Set(good.map(row=>row.ais_type))].sort((a,b)=>a-b),Array.from({length:29},(_,i)=>i));
      const binary=good.find(row=>row.ais_type===26).decoded;
      assert.equal(binary.data,'aa55');assert.equal(binary.data_bit_length,16);
      assert.equal(binary.radio,0x8abcd);assert.equal(binary.dest_mmsi,431888777);
      const reference=good.find(row=>row.ais_type===17);
      assert.equal(reference.longitude,133.82);assert.equal(reference.latitude,34.303333);
      assert(good.some(row=>row.ais_type===24&&row.decoded.callsign==='CALL123'));
      assert(good.some(row=>row.decoded.mothership_mmsi===431888777));
    }
    async function checkSource(source){
      await page.waitForFunction(async source=>{
        const rows=await fetch('/api/events?limit=100&source='+encodeURIComponent(source)).then(r=>r.json());
        return rows.length===32;
      },source,{timeout:15000});
      const response=await page.request.get('/api/events',{params:{source,limit:100}});
      assert(response.ok());const rows=await response.json();validate(rows);
      const exported=await page.request.get('/api/export/jsonl',{params:{source}});
      assert(exported.ok());validate((await exported.text()).trim().split('\n').map(line=>JSON.parse(line)));
      return rows;
    }
    for(const protocol of ['udp','tcp']){
      const before=(await (await page.request.get('/api/events?limit=1')).json())[0]?.id||0;
      await new Promise((resolve,reject)=>{
        if(protocol==='udp'){
          const sock=dgram.createSocket('udp4');sock.once('error',reject);
          sock.bind(0,'127.0.0.1',()=>{
            sock.send(payload,10110,'127.0.0.1',err=>{sock.close();if(err)reject(err);else resolve()})});
        }else{
          const sock=net.connect(10111,'127.0.0.1',()=>sock.end(payload));
          sock.once('error',reject);sock.once('close',resolve);
        }
      });
      // Docker may translate the host address and source port. Resolve the
      // durable source from the unique Type 0 fixture received after this send.
      const found=await page.waitForFunction(async({before,protocol,raw})=>{
        const rows=await fetch('/api/events?limit=200&after='+before).then(r=>r.json());
        return rows.find(row=>row.source.startsWith(protocol+':')&&row.raw===raw)?.source;
      },{before,protocol,raw:frames[0]},{timeout:15000});
      const source=await found.jsonValue();await found.dispose();
      await checkSource(source);
    }
    const uploaded=await page.request.post('/api/files?filename=ais-all-types.log',{
      data:payload,headers:{'Content-Type':'application/octet-stream'}});
    assert.equal(uploaded.status(),202);const job=await uploaded.json();
    await page.waitForFunction(async id=>{
      const jobs=await fetch('/api/jobs').then(r=>r.json());return jobs.find(job=>job.id===id)?.status==='completed';
    },job.id,{timeout:15000});
    const rows=await checkSource('file:'+job.id);
    await page.locator('#source').selectOption('file');
    await page.locator('#search').fill('ais-all-types.log');
    await page.waitForFunction(()=>document.querySelectorAll('#rows tr').length===32);
    for(let type=0;type<=28;type++){
      assert(await page.locator('#rows tr').allTextContents().then(values=>values.some(value=>value.includes('AIS Type '+type+'正常'))));
    }
    const binary=rows.find(row=>row.ais_type===26);
    await page.locator('#rows tr[data-id="'+binary.id+'"]').click();
    const detail=JSON.parse(await page.locator('#detail').textContent());
    assert.equal(detail.decoded.data,'aa55');assert.equal(detail.decoded.radio,0x8abcd);
    await page.reload();
    await page.waitForFunction(()=>identityByMmsi.get('338091445')?.shipname==='HMS FOOBAR');
    assert.equal(await page.evaluate(()=>identityByMmsi.get('338091445').shipname),'HMS FOOBAR');
    await page.locator('#source').selectOption('file');
    await page.locator('#search').fill('ais-all-types.log');
    await page.waitForFunction(()=>[...symbolRows.values()].some(row=>row.ais_type===17&&row.longitude===133.82));
    await page.evaluate(()=>{const row=[...symbolRows.values()].find(row=>row.ais_type===19);selectTrack(row)});
    await page.waitForFunction(()=>document.querySelector('#trackFields').textContent.includes('AIS Type 19'));
    assert(await page.locator('#trackFields').textContent().then(text=>text.includes('Extended Class-B')));
    assert.deepEqual(errors,[]);
    console.log('PASS: AIS Types 0-28 over UDP/TCP/file, PostgreSQL/export, Cesium and Type 24 identities');
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});
