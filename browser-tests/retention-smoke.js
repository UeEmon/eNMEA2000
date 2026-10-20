const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const token=fs.readFileSync('.env','utf8').match(/^APP_TOKEN=(.+)$/m)?.[1];
  assert(token,'APP_TOKEN missing');
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-webgl']});
  try{
    const page=await browser.newPage();
    const errors=[];page.on('pageerror',err=>errors.push(err.message));
    await page.goto('http://127.0.0.1:18081');
    await page.locator('#token').fill(token);
    await page.getByRole('button',{name:'接続する'}).click();
    await page.waitForFunction(()=>document.querySelector('#retentionSummary')?.textContent.includes('保存期間'));
    assert.equal(await page.locator('#retentionSummary').textContent(),'保存期間 24時間・自動削除 有効');
    await page.locator('#retentionOpen').click();
    await page.waitForFunction(()=>document.querySelector('#retentionDialog').open);
    assert.equal(await page.locator('#retentionHours').inputValue(),'24');
    assert(await page.locator('#retentionAuto').isChecked());
    await page.locator('#retentionHours').fill('48');
    await page.locator('#retentionAuto').uncheck();
    await page.locator('#retentionSave').click();
    await page.waitForFunction(()=>!document.querySelector('#retentionDialog').open);
    assert.equal(await page.locator('#retentionSummary').textContent(),'保存期間 48時間・自動削除 無効');
    await page.reload();
    await page.waitForFunction(()=>document.querySelector('#retentionSummary')?.textContent.includes('48時間'));
    await page.locator('#retentionOpen').click();
    await page.waitForFunction(()=>document.querySelector('#retentionDialog').open);
    assert.equal(await page.locator('#retentionHours').inputValue(),'48');
    assert(!(await page.locator('#retentionAuto').isChecked()));
    // Restore defaults for later scripts.
    await page.locator('#retentionHours').fill('24');
    await page.locator('#retentionAuto').check();
    await page.locator('#retentionSave').click();
    await page.waitForFunction(()=>document.querySelector('#retentionSummary').textContent==='保存期間 24時間・自動削除 有効');
    assert.deepEqual(errors,[]);
    console.log('retention settings OK');
  }finally{await browser.close()}
})().catch(err=>{console.error(err);process.exit(1)});
