const {chromium}=require('playwright-core');const path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await context.tracing.start({screenshots:true,snapshots:true});
 const page=await context.newPage();page.setDefaultTimeout(5000);const root=path.resolve(__dirname,'../../web');
 await page.route('http://poster.test/**',async route=>{const p=new URL(route.request().url()).pathname;if(p==='/api/jobs')return route.fulfill({json:{jobs:[]}});if(p==='/blocked.mp4')return new Promise(()=>{});if(p.includes('b'.repeat(32))&&p.endsWith('/poster'))return route.fulfill({status:404,body:'missing'});if(p.endsWith('/poster'))return route.fulfill({path:process.env.POSTER_FIXTURE});return route.fulfill({path:path.join(root,p==='/'?'index.html':p.slice(1))});});
 try{
  await page.goto('http://poster.test/');assert.equal(await page.locator('#source-poster').count(),1,'server frame fallback exists');
  await page.evaluate(()=>setUpload({id:'a'.repeat(32),url:'/blocked.mp4',name:'phone.mov',width:128,height:240,fps:24,duration:2}));
  await page.waitForFunction(()=>previewReady,undefined,{polling:100});
  assert.equal(await page.evaluate(()=>document.getElementById('source-video').readyState),0,'video deliberately unavailable');
  assert.ok(await page.locator('#source-poster').isVisible());
  await page.locator('#edit-mask').click();const box=await page.locator('#mask-canvas').boundingBox();await page.mouse.move(box.x+20,box.y+20);await page.mouse.down();await page.mouse.move(box.x+60,box.y+60);await page.mouse.up();assert.equal(await page.evaluate(()=>hasMask()),true);
  // Stale first-frame must not remain over a selected later video frame.
  await page.evaluate(()=>{const v=document.getElementById('source-video');Object.defineProperty(v,'readyState',{get:()=>2});v.dispatchEvent(new Event('loadeddata'));});
  assert.equal(await page.locator('#source-poster').isVisible(),false);
  await page.evaluate(()=>setUpload({id:'b'.repeat(32),url:'/blocked.mp4',name:'new.mov',width:128,height:240,fps:24,duration:2}));assert.equal(await page.evaluate(()=>previewReady),false);assert.equal(await page.locator('#source-poster').isVisible(),false);
  console.log('PASS: unavailable video still shows authenticated frame and allows marking; decoded video replaces poster');
 }finally{await page.unrouteAll({behavior:'ignoreErrors'});await context.tracing.stop({path:process.env.TRACE_PATH||'/tmp/poster-editor-trace.zip'});await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
