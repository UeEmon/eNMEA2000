// Sends $PADSB (eADS-B2000 output) over TCP and checks the aircraft symbol and track details.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const net=require('node:net');

function sentence(body){let cs=0;for(const c of body)cs^=c.charCodeAt(0);return '$'+body+'*'+cs.toString(16).toUpperCase().padStart(2,'0')}

(async()=>{
  const token=process.env.APP_TOKEN||fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token);
  const lines=[0,1,2].map(i=>sentence(`PADSB,86D3A1,JAL123,${(35.40+i*.05).toFixed(6)},${(139.60+i*.05).toFixed(6)},12500,420.0,45.0,-1472,3`));
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const page=await browser.newPage({baseURL:'http://127.0.0.1:18081',viewport:{width:1500,height:1000}});
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto('/');
    await page.locator('#token').fill(token);
    await page.getByRole('button',{name:'接続する'}).click();
    await page.waitForFunction(()=>active&&globe);
    await new Promise((resolve,reject)=>{const s=net.connect(10111,'127.0.0.1',()=>s.end(lines.join('\r\n')+'\r\n'));s.on('close',resolve);s.on('error',reject)});
    await page.waitForFunction(()=>[...symbolRows.values()].some(r=>r.icao==='86D3A1'),null,{timeout:15000});
    const symbol=await page.evaluate(()=>{const [entity,row]=[...symbolRows].find(([,r])=>r.icao==='86D3A1');
      return {label:entity.label.text.getValue(),image:entity.billboard.image.getValue() instanceof HTMLCanvasElement,lat:row.latitude}});
    assert.equal(symbol.label,'JAL123 FL125');assert(symbol.image);
    assert.equal(symbol.lat,35.5);
    await page.evaluate(()=>selectTrack([...symbolRows.values()].find(r=>r.icao==='86D3A1')));
    await page.waitForFunction(()=>document.getElementById('trackName').textContent==='JAL123');
    await page.waitForFunction(()=>/位置情報 [3-9]/.test(document.getElementById('trackStatus').textContent));
    const fields=await page.locator('#trackFields').innerText();
    for(const text of ['86D3A1','12500 ft','420.0 kt','45.0°','-1472 ft/min'])assert(fields.includes(text),text+' missing: '+fields);
    await page.screenshot({path:process.env.SCREENSHOT||'adsb-smoke.png'});
    assert.deepEqual(errors,[]);
    console.log('ADS-B browser smoke passed');
  }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
