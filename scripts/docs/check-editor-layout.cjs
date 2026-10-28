/* Read-only UI regression checks. Requires the four synthetic clips in HENGE_FRAME_FIXTURES.
 * Same PLAYWRIGHT_MODULE / CHROMIUM_EXECUTABLE / HENGE_GUIDE_URL options as check-guide.cjs.
 */
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.HENGE_GUIDE_URL||'http://127.0.0.1:8188';
const fixtures=process.env.HENGE_FRAME_FIXTURES||'/tmp/henge-frame-ui-fixtures';
const output=process.env.HENGE_EDITOR_CHECK_OUTPUT||'/tmp/henge-editor-check';
(async()=>{
 await fs.mkdir(output,{recursive:true});
 await fs.mkdir(fixtures,{recursive:true});
 for(const [name,width,height] of [['portrait',720,1280],['landscape',1920,1080],['square',1024,1024],['portrait4k',2160,3840]]){
  const file=path.join(fixtures,name+'.mp4');
  try{await fs.access(file)}catch{
   const result=spawnSync('ffmpeg',['-v','error','-f','lavfi','-i',`testsrc2=size=${width}x${height}:rate=2`,'-t','1','-c:v','libx264','-preset','ultrafast','-crf','30','-pix_fmt','yuv420p','-movflags','+faststart','-y',file],{encoding:'utf8'});
   if(result.status!==0)throw Error('Cannot create synthetic frame fixture: '+(result.stderr||result.error));
  }
 }

 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE,args:['--no-sandbox','--disable-dev-shm-usage']});
 const errors=[],writes=[];
 async function open(viewport,legacy=false){
  const context=await browser.newContext({viewport,colorScheme:'dark',reducedMotion:'reduce'});
  await context.route('**/api/**',async route=>{
   if(!['GET','HEAD','OPTIONS'].includes(route.request().method())){writes.push(route.request().url());return route.abort('blockedbyclient')}
   if(legacy&&new URL(route.request().url()).pathname==='/api/backend/health'){
    const response=await route.fetch();const data=await response.json();data.editor_ready=true;delete data.frame_editor;
    return route.fulfill({response,json:data});
   }
   return route.continue();
  });
  await context.addInitScript(()=>{if(!['http:','https:'].includes(location.protocol))return;localStorage.setItem('henge-setup-done','1');localStorage.setItem('henge-draft',JSON.stringify({lang:'pt',mode:'motion'}));});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base,{waitUntil:'networkidle'});await page.locator('#generation-seed').waitFor();return{page,context};
 }
 try{
  const settings=await open({width:1280,height:900});
  await settings.page.getByRole('button',{name:'Configurações',exact:true}).click();
  await settings.page.locator('.settings-tabs').getByRole('button',{name:'Molmo2',exact:true}).click();
  await settings.page.getByText('Usar o Molmo2',{exact:false}).waitFor();
  assert.equal(await settings.page.locator('.molmo-settings select').count(),0);
  assert.equal(await settings.page.locator('.molmo-settings .select-button').count(),2);
  await settings.page.locator('.molmo-settings .select-button').first().click();
  await settings.page.getByRole('listbox').waitFor({state:'visible'});
  await settings.page.screenshot({path:path.join(output,'molmo-dropdown.png')});
  await settings.page.keyboard.press('Escape');await settings.context.close();
  for(const viewport of [{width:1280,height:900},{width:900,height:700},{width:390,height:844}]){
   for(const name of ['portrait','landscape','square','portrait4k']){
    const {page,context}=await open(viewport);
    try{
     await page.getByTestId('guide-input').setInputFiles(path.join(fixtures,name+'.mp4'));
     await page.getByRole('button',{name:'Confirm interval →',exact:true}).click();
     await page.locator('.ffp-card').evaluate(e=>{e.open=true});
     await page.getByRole('button',{name:'Escolher e editar um quadro',exact:true}).click();
     await page.locator('.first-frame-paint img').waitFor({timeout:30000});
     await page.locator('.first-frame-controls textarea').waitFor({timeout:30000});
     const geometry=await page.locator('.first-frame-modal').evaluate(modal=>{
      const rect=selector=>{const r=modal.querySelector(selector).getBoundingClientRect();return{x:r.x,y:r.y,right:r.right,bottom:r.bottom,width:r.width,height:r.height}};
      return{panes:rect('.first-frame-panes'),form:rect('.first-frame-form'),chooser:rect('.frame-chooser'),controls:rect('.first-frame-controls'),body:rect('.first-frame-body'),footer:rect('.first-frame-footer'),viewport:innerHeight};
     });
     const overlaps=(a,b)=>Math.min(a.right,b.right)-Math.max(a.x,b.x)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.y,b.y)>1;
     assert.equal(overlaps(geometry.panes,geometry.form),false,`Preview/form overlap: ${name} ${viewport.width}`);
     assert.equal(overlaps(geometry.chooser,geometry.controls),false,`Chooser/fields overlap: ${name} ${viewport.width}`);
     assert.ok(geometry.body.bottom<=geometry.footer.y+1,'Scroll body crosses footer');
     assert.ok(geometry.footer.bottom<=geometry.viewport+1,'Footer outside viewport');
     assert.doesNotMatch(await page.locator('.first-frame-modal').innerText(),/FIBO/i);
     await page.locator('.first-frame-modal').screenshot({path:path.join(output,`${name}-${viewport.width}.png`)});
     console.log(`Passed ${name} at ${viewport.width}×${viewport.height}`);
    }finally{await context.close()}
   }
  }
  const legacy=await open({width:1280,height:900},true);
  await legacy.page.getByText('Editor de imagem',{exact:true}).waitFor();
  assert.doesNotMatch(await legacy.page.locator('.generation-settings-card').innerText(),/FIBO/i);
  await legacy.context.close();
  assert.deepEqual(writes,[]);assert.deepEqual(errors,[]);
  console.log('Passed: themed Molmo dropdowns, 12 editor geometry cases, unknown backend label, no API writes or browser errors.');
  console.log('Screenshots: '+output);
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
