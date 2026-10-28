/* Read-only Playwright checks for the visual guide. Uses the same browser env vars as capture-guide.cjs. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.HENGE_GUIDE_URL || 'http://127.0.0.1:8188';
const output = process.env.HENGE_GUIDE_CHECK_OUTPUT || path.join(os.tmpdir(), 'henge-guide-check');
(async () => {
  await fs.mkdir(output, {recursive: true});
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_EXECUTABLE ? {executablePath: process.env.CHROMIUM_EXECUTABLE} : {}), args: ['--no-sandbox']});
  const errors = [];
  try {
    const context = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce', permissions: ['clipboard-read', 'clipboard-write']});
    await context.addInitScript(() => {if (!['http:', 'https:'].includes(location.protocol)) return;localStorage.setItem('henge-setup-done', '1');localStorage.setItem('henge-draft', JSON.stringify({lang: 'pt', mode: 'motion'}));});
    const app = await context.newPage();app.on('pageerror', e => errors.push(e.message));
    await app.goto(base, {waitUntil: 'networkidle'});
    const tips = app.getByRole('link', {name: 'Dicas', exact: true});
    assert.equal(await tips.getAttribute('href'), '/guides/index.html');
    const popup = context.waitForEvent('page');await tips.click();const page = await popup;
    page.on('pageerror', e => errors.push(e.message));
    await page.waitForLoadState('networkidle');
    assert.match(await page.title(), /Dicas de uso/);
    const missingAnchors = await page.locator('a[href^="#"]').evaluateAll(links => links.map(a => a.hash.slice(1)).filter(id => !document.getElementById(id)));
    assert.deepEqual(missingAnchors, []);
    const manifestResponse = await context.request.get(base + '/guides/images/capture-manifest.json');
    assert.equal(manifestResponse.status(), 200);const manifest = await manifestResponse.json();
    assert.equal(manifest.images.length, 24);assert.deepEqual(manifest.browser_errors, []);assert.deepEqual(manifest.api_writes_blocked, []);
    for (const image of manifest.images) assert.equal((await context.request.get(base + '/guides/images/' + image)).status(), 200, image);
    assert.equal(await page.locator('img:not([alt]),img[alt=""]').count(), 1); // Empty zoom viewer; all document images are described.
    await page.locator('a.zoom').first().click();
    assert.equal(await page.locator('#image-viewer').evaluate(d => d.open), true);
    await page.keyboard.press('Escape');assert.equal(await page.locator('#image-viewer').evaluate(d => d.open), false);
    await page.getByText('Ver um exemplo completo para Motion Transfer TARA', {exact: true}).click();
    await page.locator('[data-copy]').click();
    await page.waitForFunction(() => document.querySelector('[data-copy]').textContent.includes('Copiado'), null, {timeout: 5000});
    assert.match(await page.locator('[data-copy]').innerText(), /Copiado/);
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assert.match(copied, /GREEN-marked/);assert.doesNotMatch(copied, /front left|front right|behind the purple/);
    await page.getByText('Ver um exemplo completo para Motion Transfer TARA', {exact: true}).click();
    await page.evaluate(() => window.scrollTo(0, 0));await page.screenshot({path: path.join(output, 'desktop.png')});
    const mobile = await context.newPage();mobile.on('pageerror', e => errors.push(e.message));
    await mobile.setViewportSize({width: 390, height: 844});await mobile.goto(base + '/guides/index.html', {waitUntil: 'networkidle'});
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'Mobile page overflows horizontally');
    await mobile.screenshot({path: path.join(output, 'mobile.png')});
    await mobile.locator('aside nav a[href="#seed"]').click();
    await mobile.locator('#seed').screenshot({path: path.join(output, 'mobile-seed.png')});
    assert.equal(await mobile.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true);
    await app.setViewportSize({width:390,height:844});
    assert.equal(await tips.isVisible(), true, 'Tips link should remain available on mobile');
    assert.deepEqual(errors, []);
    console.log('Passed: studio link, 24 screenshot assets, anchors, zoom, prompt copy, mobile layout and browser errors.');
    console.log('Review screenshots: ' + output);
  } finally {await browser.close();}
})().catch(e => {console.error(e);process.exit(1);});
