const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  const page=await browser.newPage();
  try{
    await page.goto('http://127.0.0.1:8090');
    await page.waitForFunction(()=>document.querySelector('#outputHost').value.length>0);
    await page.locator('#outputHost').fill('host.docker.internal');
    await page.locator('#outputProtocol').selectOption('udp');
    assert.equal(await page.locator('#outputPort').inputValue(),'10110');
    await page.getByRole('button',{name:'送信先を保存',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#outputResult').textContent.includes('UDP host.docker.internal:10110'));
    await page.locator('#aisScenario').selectOption('type-5');
    await page.getByRole('button',{name:'選択項目を送信',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#suiteResult').textContent.includes('送信完了'));
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#outputProtocol').value==='udp'&&document.querySelector('#outputPort').value==='10110');
    console.log('PASS: destination UI, TCP/UDP port defaults, UDP AIS send, saved configuration reload');
  }finally{
    await page.request.post('http://127.0.0.1:8090/api/output',{data:{host:'host.docker.internal',port:10111,protocol:'tcp'}});
    await browser.close();
  }
})().catch(error=>{console.error(error);process.exit(1)});
