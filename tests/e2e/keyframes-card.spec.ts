import {expect, test, type Page} from '@playwright/test';

/** The Keyframes card: shots and camera cuts on a timeline, a ◇ suggestion at each cut, and a compact layout on a phone.
    No generation runs. HENGE_E2E_GUIDE should hold a camera cut.

    HENGE_E2E_GUIDE=/path/to/clip-with-a-cut.mp4 HENGE_E2E_PICTURE=/path/to/character.png \
    HENGE_E2E_BASE=http://127.0.0.1:8188 npx playwright test tests/e2e/keyframes-card.spec.ts
*/
const BASE = process.env.HENGE_E2E_BASE || 'http://127.0.0.1:8188';
const GUIDE = process.env.HENGE_E2E_GUIDE || '';
const PICTURE = process.env.HENGE_E2E_PICTURE || '';

async function openStudio(page: Page) {
  await page.addInitScript(() => {try {localStorage.setItem('henge-setup-done', '1');} catch {/* private browsing */}});
  await page.goto(BASE, {waitUntil: 'domcontentloaded'});
  const skip = page.getByRole('button', {name: /Skip setup|Pular configuração|Saltar configuración/});
  if (await skip.count()) await skip.click();
  await expect(page.locator('.settings-backdrop')).toHaveCount(0);
}

async function continuePastMissingModels(page: Page) {
  const go = page.getByRole('button', {name: /^(Continue with|Continuar com|Continuar con)/}).first();
  // The checklist opens once the inventory loads; give it a moment, then let it go.
  await go.waitFor({state: 'visible', timeout: 15_000}).then(() => go.click(), () => undefined);
}

for (const [name, viewport] of [['desktop', {width: 1440, height: 900}], ['phone', {width: 390, height: 844}]] as const) {
  test(`keyframes card shows shots, cuts and suggestions (${name})`, async ({page}) => {
    test.skip(!GUIDE || !PICTURE, 'needs HENGE_E2E_GUIDE and HENGE_E2E_PICTURE');
    test.setTimeout(180_000);
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(String(error)));
    await page.setViewportSize(viewport);
    await openStudio(page);
    await continuePastMissingModels(page);
    const swap = page.locator('.mode-switch button').first();
    await expect(swap).toBeEnabled({timeout: 60_000});
    await swap.click();
    await page.locator('[data-testid=guide-input]').setInputFiles(GUIDE);
    const trim = page.locator('.trim-overlay');
    await expect(trim).toBeVisible({timeout: 30_000});
    await trim.getByRole('button', {name: /Use full video|Usar o vídeo inteiro|Usar video completo/}).click();
    await page.locator('[data-testid=picture-input]').setInputFiles(PICTURE);
    await continuePastMissingModels(page);
    const card = page.locator('.keyframes-card');
    await expect(card).toBeVisible({timeout: 40_000});
    await card.locator('> summary').click();

    // The card stays small: a count of the cuts without a keyframe; the timeline itself lives in the frame editor.
    const hint = card.locator('.kf-hint');
    await expect(hint).toBeVisible({timeout: 60_000});
    await card.scrollIntoViewIfNeeded();
    await card.screenshot({path: `test-results/keyframes-card-${name}.png`});

    // The card never makes the page scroll sideways on a phone.
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);

    // The hint opens the frame editor, with the shots, cuts and suggestions on its timeline.
    await hint.click();
    const modal = page.locator('.first-frame-modal');
    await expect(modal).toBeVisible();
    // FFP-style: with no first frame yet, the start is pinned first; the cut is a keyframe.
    await expect(modal.locator('#first-frame-heading')).toHaveText(/Swap the character|Coloque o personagem|Pon al personaje/);
    const timeline = modal.locator('.ff-timeline');
    // The editor is on the start already, so only the cut is still suggested.
    await expect(timeline.locator('.kf-pin.suggest')).toHaveCount(1);
    await modal.getByRole('button', {name: /Next cut without a keyframe|Próximo corte sem keyframe|Siguiente corte sin keyframe/}).click();
    await expect(modal.locator('#first-frame-heading')).toHaveText(/Pin a keyframe|Fixar um keyframe|Fijar un keyframe/);
    // Past the start the frame can also open the clip (the person may not be in frame 0).
    await modal.getByRole('button', {name: /Start the clip here|Começar o vídeo aqui|Empezar el vídeo aquí/}).click();
    await expect(modal.locator('#first-frame-heading')).toHaveText(/Swap the character|Coloque o personagem|Pon al personaje/);
    await expect(modal.getByRole('button', {name: /Use as first frame|Usar como primeiro|Usar como primer/})).toBeVisible();
    await modal.getByRole('button', {name: /Pin as a keyframe|Fixar como keyframe|Fijar como keyframe/}).click();
    await expect(modal.locator('#first-frame-heading')).toHaveText(/Pin a keyframe|Fixar um keyframe|Fijar un keyframe/);
    await expect(timeline.locator('.kf-shot').first()).toBeAttached();
    await expect(timeline.locator('.kf-cut')).not.toHaveCount(0);
    await expect(timeline.locator('.kf-pin.suggest').first()).toBeVisible();
    await expect(modal.getByRole('button', {name: /Pin this frame|Fixar este quadro|Fijar este fotograma/})).toBeVisible();
    // The editor picker opens above the dialog and lists every installed editor.
    const picker = modal.getByRole('button', {name: /^(Image editor|Editor de imagem|Editor de imagen)$/});
    if (await picker.count()) {await picker.click(); await expect(page.getByRole('listbox')).toBeVisible(); await page.keyboard.press('Escape');}
    await page.screenshot({path: `test-results/keyframes-modal-${name}.png`});
    expect(errors).toEqual([]);
  });
}
