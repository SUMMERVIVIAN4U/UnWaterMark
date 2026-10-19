// Requires playwright-core via NODE_PATH, a hosted HTTPS test server and synthetic VIDEO_FIXTURE.
const {chromium}=require('playwright-core');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const options={ignoreHTTPSErrors:true,viewport:{width:390,height:844},isMobile:true,hasTouch:true};
 const a=await browser.newContext(options),b=await browser.newContext(options);await a.tracing.start({screenshots:true,snapshots:true,sources:true});
 const page=await a.newPage();page.setDefaultTimeout(60000);const base=process.env.TEST_URL||'https://127.0.0.1:8771';
 try{
  await page.goto(base);await page.waitForFunction(()=>csrf!==null);assert.equal((await a.request.get(base+'/api/jobs')).status(),200);
  await page.locator('#file-input').setInputFiles(process.env.VIDEO_FIXTURE);
  await page.waitForFunction(()=>upload&&previewReady,undefined,{polling:100});const uploadId=await page.evaluate(()=>upload.id);
  assert.equal(await page.locator('#edit-mask').count(),0);const box=await page.locator('#mask-canvas').boundingBox();
  await page.mouse.move(box.x+15,box.y+15);await page.mouse.down();await page.mouse.move(box.x+40,box.y+40);await page.mouse.up();
  await page.locator('#submit-full').click();await page.waitForFunction(()=>job?.status==='succeeded'||job?.status==='failed',undefined,{polling:300});
  const job=await page.evaluate(()=>window.eval('job'));assert.equal(job.status,'succeeded',job.error);
  assert.equal(await page.locator('#preview-badge').isVisible(),true);
  assert.ok((await page.locator('#result-video').getAttribute('src')).endsWith('/preview'));
  assert.equal((await a.request.get(base+job.result_url)).status(),403);
  await page.locator('#export-password').fill('incorrect');await page.locator('#unlock-export').click();await page.waitForFunction(()=>document.getElementById('export-message').textContent.includes('不正确'));
  await page.locator('#export-password').fill(process.env.EXPORT_TEST_PASSWORD||'browser-test-password');await page.locator('#unlock-export').click();await page.waitForFunction(()=>exportUnlocked);assert.equal(await page.locator('#preview-badge').isVisible(),false);
  assert.equal((await a.request.get(base+job.result_url,{headers:{Range:'bytes=0-15'}})).status(),206);
  const other=await b.newPage();await other.goto(base);await other.waitForFunction(()=>csrf!==null);
  assert.deepEqual((await (await b.request.get(base+'/api/jobs')).json()).jobs,[]);
  assert.equal((await b.request.get(base+'/api/uploads/'+uploadId+'/video')).status(),404);
  const token=await other.evaluate(()=>csrf);await b.request.post(base+'/api/export/unlock',{headers:{'X-CSRF-Token':token},data:{password:process.env.EXPORT_TEST_PASSWORD||'browser-test-password'}});
  assert.equal((await b.request.get(base+job.result_url)).status(),404);
  await page.reload();await page.waitForFunction(()=>csrf!==null);assert.ok((await (await a.request.get(base+'/api/jobs')).json()).jobs.some(j=>j.id===job.id));
  await a.clearCookies();await page.reload();await page.waitForFunction(()=>csrf!==null);assert.deepEqual((await (await a.request.get(base+'/api/jobs')).json()).jobs,[]);
  console.log('PASS: upload → mark → process → marked preview → wrong password → unlock → range export; second browser isolation; reload persists; cleared cookies cannot recover');
 }finally{await a.tracing.stop({path:process.env.TRACE_PATH||'/tmp/private-export-trace.zip'});await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
