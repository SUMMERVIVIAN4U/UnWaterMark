// Run with NODE_PATH pointing to a playwright-core installation.
const {chromium}=require('playwright-core');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:true});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 await context.tracing.start({screenshots:true,snapshots:true,sources:true});
 const page=await context.newPage();page.setDefaultTimeout(20000);let retryRequests=0,retryAllowed=false;const web=path.resolve(__dirname,'../../web');
 await page.route('http://editor.test/**',async route=>{const url=new URL(route.request().url());if(url.pathname.endsWith('/poster'))return route.fulfill({status:404,body:'No poster in this loading test'});if(url.pathname==='/api/jobs')return route.fulfill({json:{jobs:[]}});if(url.pathname==='/retry.mp4'){retryRequests++;if(!retryAllowed)return route.fulfill({status:503,body:'Unavailable'});return route.fulfill({path:process.env.VIDEO_FIXTURE,contentType:'video/mp4'});}if(url.pathname==='/sample.mp4')return route.fulfill({path:process.env.VIDEO_FIXTURE,contentType:'video/mp4'});if(url.pathname==='/blocked.mp4')return new Promise(()=>{});const file=url.pathname==='/'?'index.html':url.pathname.slice(1);return route.fulfill({path:path.join(web,file)});});
 try{
 await page.goto('http://editor.test/');
 await page.evaluate(()=>setUpload({id:'a',url:'/blocked.mp4',name:'test.mov',width:720,height:1280,fps:24,duration:10}));
 // A missing/not decoded video must not accept marks, even synthetic touch input.
 await page.locator('#mask-canvas').dispatchEvent('pointerdown',{pointerId:1,pointerType:'touch',isPrimary:true,clientX:100,clientY:200});
 await page.locator('#mask-canvas').dispatchEvent('pointermove',{pointerId:1,pointerType:'touch',clientX:160,clientY:260});
 assert.equal(await page.evaluate(()=>hasMask()),false,'unready preview must not draw');
 assert.equal(await page.locator('#preview-start').count(),1,'explicit preview activation required');
 // Simulate a decoded paused frame independently of mobile codec/network policy.
 await page.evaluate(()=>{setUpload({id:'b',url:'/blocked.mp4',name:'test.mov',width:720,height:1280,fps:24,duration:10});const v=document.getElementById('source-video');Object.defineProperty(v,'readyState',{get:()=>2,configurable:true});v.dispatchEvent(new Event('loadeddata'));});
 assert.equal(await page.evaluate(()=>canvas.dataset.editing),'false');
 await page.locator('#edit-mask').click();
 const box=await page.locator('#mask-canvas').boundingBox();
 await page.mouse.move(box.x+30,box.y+40);await page.mouse.down();await page.mouse.move(box.x+90,box.y+120);await page.mouse.up();
 assert.equal(await page.evaluate(()=>hasMask()),true,'explicit editing draws');
 const before=await page.evaluate(()=>mask.toDataURL());
 await page.locator('#mask-canvas').dispatchEvent('pointerdown',{pointerId:3,pointerType:'touch',isPrimary:true,clientX:box.x+100,clientY:box.y+150});
 await page.locator('#mask-canvas').dispatchEvent('pointermove',{pointerId:3,pointerType:'touch',clientX:box.x+150,clientY:box.y+200});
 await page.locator('#mask-canvas').dispatchEvent('pointercancel',{pointerId:3});
 assert.equal(await page.evaluate(()=>mask.toDataURL()),before,'canceled gesture rolls back');
 await page.locator('#edit-mask').click();assert.equal(await page.evaluate(()=>canvas.dataset.editing),'false');
 const dims=await page.evaluate(()=>{const v=document.getElementById('source-video').getBoundingClientRect(),c=canvas.getBoundingClientRect();return {vw:v.width,vh:v.height,cw:c.width,ch:c.height};});
 assert.ok(Math.abs(dims.vw-dims.cw)<1&&Math.abs(dims.vh-dims.ch)<1,'overlay matches video');
 assert.ok(dims.ch<510,'portrait editor fits phone');
 if(process.env.VIDEO_FIXTURE){
 await page.evaluate(()=>{delete document.getElementById('source-video').readyState;setUpload({id:'c',url:'/sample.mp4',name:'sample.mp4',width:160,height:128,fps:24,duration:2});});
 await page.waitForFunction(()=>document.getElementById('source-video').readyState>=2,undefined,{polling:100});
 assert.equal(await page.locator('#edit-mask').isEnabled(),true);
 await page.locator('#play-toggle').click();await page.waitForFunction(()=>document.getElementById('source-video').currentTime>0,undefined,{polling:100});
 await page.locator('#edit-mask').click();assert.equal(await page.evaluate(()=>document.getElementById('source-video').paused),true);
 await page.evaluate(()=>setUpload({id:'d',url:'/retry.mp4',name:'retry.mp4',width:160,height:128,fps:24,duration:2}));
 await page.waitForFunction(()=>document.getElementById('source-video').error!==null,undefined,{polling:100});
 retryAllowed=true;await page.locator('#preview-start').click();
 await page.waitForFunction(()=>document.getElementById('source-video').readyState>=2&&document.getElementById('source-video').paused,undefined,{polling:100});
 assert.equal(await page.locator('#edit-mask').isEnabled(),true,'retry recovers decoded preview');
 const pixel=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=160;c.height=128;const x=c.getContext('2d');x.drawImage(document.getElementById('source-video'),0,0);return [...x.getImageData(0,0,160,128).data].filter((v,i)=>i%4!==3).some(v=>v>30);});assert.ok(pixel,'decoded video contains visible pixels');
 }
 console.log('PASS: unready guard, explicit editing, draw, cancel rollback, scroll mode, portrait alignment');
 }catch(e){console.error('TEST FAILURE',e,await page.evaluate(()=>({state:document.getElementById('source-video').readyState,paused:document.getElementById('source-video').paused,error:document.getElementById('source-video').error?.message,status:document.getElementById('preview-status').textContent,alert:document.getElementById('error-message').textContent})),retryRequests);throw e;}finally{await page.unrouteAll({behavior:'ignoreErrors'});await context.tracing.stop({path:process.env.TRACE_PATH||'/tmp/mobile-editor-trace.zip'});await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
