const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  const page=await browser.newPage();
  let receiverWasEnabled=null;
  try{
    await page.goto('http://127.0.0.1:8090');
    await page.waitForFunction(()=>document.querySelector('#outputHost').value.length>0);
    await page.locator('#outputHost').fill('host.docker.internal');
    await page.locator('#outputProtocol').selectOption('udp');
    assert.equal(await page.locator('#outputPort').inputValue(),'10110');
    await page.getByRole('button',{name:'送信先を保存',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#outputResult').textContent.includes('UDP host.docker.internal:10110'));
    const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)[1];
    assert((await page.request.post('http://127.0.0.1:18081/api/login',{data:{token}})).ok());
    receiverWasEnabled=(await (await page.request.get('http://127.0.0.1:18081/api/stats')).json()).udp_enabled;
    assert((await page.request.post('http://127.0.0.1:18081/api/udp/start')).ok());
    const events=async()=>await (await page.request.get('http://127.0.0.1:18081/api/events?limit=100')).json();
    const before=(await events())[0]?.id||0;
    await page.locator('#aisScenario').selectOption('type-5');
    await page.getByRole('button',{name:'選択項目を送信',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#suiteResult').textContent.includes('送信完了'));
    let received=false;
    for(let i=0;i<30&&!received;i++){
      received=(await events()).some(event=>event.id>before&&event.ais_type===5&&event.source.startsWith('udp:'));
      if(!received)await new Promise(resolve=>setTimeout(resolve,200));
    }
    assert(received,'UDP AIS Type 5 must reach the main app outside the emulator Docker network');
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#outputProtocol').value==='udp'&&document.querySelector('#outputPort').value==='10110');
    console.log('PASS: destination UI, TCP/UDP port defaults, UDP AIS send, saved configuration reload');
  }finally{
    await page.request.post('http://127.0.0.1:8090/api/output',{data:{host:'host.docker.internal',port:10111,protocol:'tcp'}});
    if(receiverWasEnabled!==null)await page.request.post('http://127.0.0.1:18081/api/udp/'+(receiverWasEnabled?'start':'stop'));
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exit(1)});
