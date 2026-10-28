/* Capture real Henge UI in an isolated browser; API writes are blocked.
 * PLAYWRIGHT_MODULE=/path/to/playwright CHROMIUM_EXECUTABLE=/path/to/chrome node scripts/docs/capture-guide.cjs
 * Optional: HENGE_GUIDE_URL, HENGE_GUIDE_JOB, HENGE_CHARACTER_JOB, HENGE_MARKS_JOB.
 * Uses existing completed Maverick tests by default. Does not submit generation, Molmo or assistant requests.
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.HENGE_GUIDE_URL || 'http://127.0.0.1:8188';
const directory = path.resolve(__dirname, '../../public/guides/images');
const captured = [], errors = [], blockedWrites = [];

async function main() {
  await fs.mkdir(directory, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {}), args: ['--no-sandbox']});
  try {
    const api = await browser.newContext();
    const response = await api.request.get(base + '/api/backend/jobs');
    if (!response.ok()) throw Error('Cannot read existing jobs: ' + response.status());
    const jobs = await response.json();
    const find = (env, profile) => process.env[env] || jobs.find(j => j.status === 'completed' && j.options?.profile === profile && /Maverick.*prompt explícito/i.test(j.project || ''))?.id;
    const tara = find('HENGE_GUIDE_JOB', 'motion_tara');
    const character = find('HENGE_CHARACTER_JOB', 'character');
    const full = process.env.HENGE_FULL_JOB || jobs.find(j => j.id === 'c20d487d89004c3ba9949f4ec399daa9')?.id;
    const marks = process.env.HENGE_MARKS_JOB || jobs.find(j => j.marks_preview_url && /Maverick/i.test(j.project || ''))?.id;
    if (!tara || !character) throw Error('Set HENGE_GUIDE_JOB and HENGE_CHARACTER_JOB to existing completed test jobs.');
    await api.close();

    async function openJob(id) {
      const context = await browser.newContext({viewport: {width: 1440, height: 1000}, deviceScaleFactor: 1, colorScheme: 'light'});
      await context.route('**/api/**', route => {
        if (['GET', 'HEAD', 'OPTIONS'].includes(route.request().method())) return route.continue();
        blockedWrites.push({method: route.request().method(), path: new URL(route.request().url()).pathname});
        return route.abort('blockedbyclient');
      });
      await context.addInitScript(({id}) => {
        localStorage.setItem('henge-setup-done', '1');
        localStorage.setItem('henge-selected-job', id);
        localStorage.setItem('henge-draft', JSON.stringify({lang: 'pt', mode: 'motion', project: 'Guia visual'}));
      }, {id});
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(base, {waitUntil: 'networkidle', timeout: 60000});
      const h264 = await page.evaluate(() => document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"'));
      if (!h264) throw Error('This browser cannot decode H.264. Set CHROMIUM_EXECUTABLE to Chrome for Testing or Google Chrome.');
      await page.locator('.generation-job').waitFor({timeout: 30000});
      await page.locator('section[aria-label="Personagens e referências"]').waitFor({timeout: 30000});
      await page.locator('.reference-dropzone img').first().waitFor({timeout: 30000});
      await page.evaluate(() => document.fonts.ready);
      if (await page.locator('.finished-preview video').count()) await page.locator('.finished-preview video').evaluate(v => new Promise((resolve,reject) => {if(v.readyState >= 2) return resolve();v.addEventListener('loadeddata',resolve,{once:true});setTimeout(()=>reject(Error('Result video did not load')),25000);}));
      return {page, context};
    }
    async function seek(page, seconds = .82) {
      await page.locator('video').evaluateAll(async (videos, seconds) => {
        await Promise.all(videos.filter(v => v.readyState > 0 && Number.isFinite(v.duration)).map(v => new Promise(resolve => {
          v.pause(); v.addEventListener('seeked', resolve, {once: true});
          v.currentTime = Math.min(seconds, Math.max(0, v.duration - .05)); setTimeout(resolve, 1200);
        })));
      }, seconds);
    }
    async function capture(page, name, selector) {
      const filename = name + '.png';
      if (selector) {
        const element = page.locator(selector).first();
        await element.scrollIntoViewIfNeeded();
        await element.screenshot({path: path.join(directory, filename), animations: 'disabled'});
      } else {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({path: path.join(directory, filename), animations: 'disabled'});
      }
      captured.push(filename);
      console.log('Captured ' + filename);
    }

    const first = await openJob(tara);
    const page = first.page;
    await seek(page);
    await capture(page, '01-estudio');
    await capture(page, '02-referencias', '.reference-dropzone');
    await capture(page, '03-tara-seed', '.generation-settings-card');
    await capture(page, '04-seed', '.seed-control');
    await capture(page, '05-marcas', 'section[aria-label="Personagens e referências"]');
    await page.getByRole('textbox',{name:'Execution prompt'}).fill('Verde → @Picture1: boné com detalhes dourados e óculos.\nRoxo → @Picture2: cabelo descoberto e óculos.\nCiano → @Picture3: boné azul-marinho, sem óculos.\nMantenha a identidade ligada à cor ao mudar de posição ou ficar de costas. Preserve pose, câmera e pessoas sem marcação.');
    await capture(page, '06-prompt', '.prompt-card');
    await page.locator('.generation-job .job-section').first().evaluate(e => {e.open = true;});
    await capture(page, '07-revisar-plano', '.generation-job .job-section');
    await seek(page, 1.8);
    await capture(page, '08-resultado', '.finished-preview');
    await page.getByRole('button', {name: 'Guia + resultado + referências', exact: true}).click();
    const comparison = page.locator('.finished-preview video');
    await comparison.evaluate(v => new Promise((resolve,reject) => {if (v.readyState >= 2) return resolve(); v.addEventListener('loadeddata', resolve, {once: true});setTimeout(() => reject(Error('Comparison video did not load')), 20000);}));
    await seek(page, 1.8);
    await capture(page, '09-comparacao', '.finished-preview');
    await page.getByRole('button', {name: 'Editar intervalo do vídeo', exact: true}).click();
    await page.getByRole('heading', {name: 'Choose your performance'}).waitFor();
    await capture(page, '10-intervalo', '.trim-modal');
    await page.getByRole('button', {name: 'Cancel video selection'}).click();
    await capture(page, '11-shots', '.controls .input-card');
    await page.getByRole('button', {name: 'Configurações', exact: true}).click();
    await page.locator('.settings-tabs').getByRole('button', {name: 'Molmo2', exact: true}).click();
    await page.getByText('Usar o Molmo2', {exact: false}).waitFor();
    await capture(page, '12-molmo', '.settings-center');
    await page.locator('.settings-close').click();
    await capture(page, '20-novo-cenario', '.background-card');
    await capture(page, '21-audio-saida', '.output-settings');
    const firstFrame=page.locator('.reference-dropzone details').first();
    if(await firstFrame.count()){
      await firstFrame.evaluate(e=>{e.open=true});
      await capture(page,'22-primeiro-quadro','.reference-dropzone');
      await firstFrame.evaluate(e=>{e.open=false});
    }
    await page.locator('details.generation-advanced').evaluate(e=>{e.open=true});
    await capture(page,'23-avancado','.generation-settings-card');
    await page.locator('details.generation-advanced').evaluate(e=>{e.open=false});

    await page.getByRole('button', {name: /Assistente$/}).click();
    await page.locator('.assistant-panel').waitFor();
    await page.getByRole('button',{name:'Nova conversa',exact:true}).click();
    await capture(page, '17-assistente', '.assistant-panel');
    await page.locator('.assistant-fab').click();
    await page.locator('.main-nav').getByRole('button',{name:'Histórico',exact:true}).click();
    await page.locator('.history-search').fill('Maverick');
    await page.evaluate(()=>window.scrollTo(0,0));
    await capture(page,'24-historico');

    await first.context.close();

    const second = await openJob(character);
    await capture(second.page, '13-prompt-multiplos', 'section[aria-label="Personagens e referências"]');
    await second.page.locator('section[aria-label="Personagens e referências"]').getByRole('button',{name:'MASK',exact:true}).click();
    await capture(second.page, '19-mascara', 'section[aria-label="Personagens e referências"]');
    await second.page.locator('.mode-picker button').filter({hasText:'Troca de cabeça'}).click();
    const guideButton=second.page.getByRole('button',{name:'Guide Latents',exact:true});
    if(await guideButton.count()) await guideButton.click();
    await capture(second.page, '15-head-swap', '.generation-settings-card');
    await second.page.locator('.mode-picker button').filter({hasText:'Nitidez'}).click();
    await capture(second.page, '16-nitidez', '.output-settings');
    await second.context.close();

    if (marks) {
      const third = await openJob(marks);
      const preview = third.page.locator('.marks-preview');
      if (await preview.count()) {
        await seek(third.page);
        await capture(third.page, '14-previa-mascaras', '.marks-preview');
      }
      await third.context.close();
    }
    if(full){
      const fourth=await openJob(full);
      const shots=fourth.page.locator('.shot-plan');
      await shots.waitFor({timeout:30000});
      await shots.locator('video').evaluateAll(async videos=>{
        await Promise.all(videos.map(async v=>{
          if(v.readyState<1) await new Promise((resolve,reject)=>{v.addEventListener('loadedmetadata',resolve,{once:true});setTimeout(()=>reject(Error('Shot metadata did not load')),15000)});
          const match=v.src.match(/#t=([\d.]+),([\d.]+)/);if(!match) return;
          const time=Math.min(Number(match[1])+.2,Number(match[2])-.05);
          await new Promise((resolve,reject)=>{v.addEventListener('seeked',resolve,{once:true});v.currentTime=time;v.pause();setTimeout(()=>reject(Error('Shot frame did not load')),10000)});
        }));
      });

      await capture(fourth.page,'18-shots-por-corte','.shot-plan');
      await fourth.context.close();
    }
    await fs.writeFile(path.join(directory, 'capture-manifest.json'), JSON.stringify({captured_at: new Date().toISOString(), viewport: '1440×1000', jobs: {tara, character, marks}, images: captured, api_writes_blocked: blockedWrites, browser_errors: errors, note: 'Real UI captures from existing jobs; isolated browser storage. No new AI generations. The prompt editor example is an unsent draft in the isolated browser.'}, null, 2) + '\n');
    if (errors.length) throw Error('Browser errors: ' + errors.join('; '));
    console.log(`Finished: ${captured.length} screenshots; ${blockedWrites.length} blocked API writes.`);
  } finally {await browser.close();}
}
main().catch(e => {console.error(e); process.exit(1);});
