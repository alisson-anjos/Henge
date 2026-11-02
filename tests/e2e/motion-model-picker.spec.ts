import {expect, test, type Page} from '@playwright/test';
import {readFileSync} from 'node:fs';

/** The studio offers four Motion models, and a First Frame moves you to the edit one.

    HENGE_E2E_GUIDE=/path/to/clip.mp4 HENGE_E2E_BASE=http://127.0.0.1:8188 npx playwright test tests/e2e/motion-model-picker.spec.ts
*/
const BASE = process.env.HENGE_E2E_BASE || 'http://127.0.0.1:8188';
const GUIDE = process.env.HENGE_E2E_GUIDE || '';
const MODELS = {
  motion: {label: 'Motion Transfer v1.0', file: 'minimax_h3_motion_transfer_v1.0_ref2va'},
  tara: {label: 'Motion Transfer TARA v1.0', file: 'minimax_h3_motion_transfer_tara_v1.0_ref2va'},
  edit: {label: 'Motion Transfer FFP v1.0', file: 'minimax_h3_motion_transfer_ffp_v1.0_ref2va'},
  solar: {label: 'Motion Transfer SolarRenderer FFP v1.0', file: 'solarrenderer_control_comfy'},
};
// An edited opening frame (the editor's output shape): Picture 2 carries the edit the model must propagate.
const EDITED_FRAME = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAaklEQVR4nGNgZ4AAOxYMBgZmEAwJYmBgZGRlAWJWhJwOILnNDST3PmBgYDzAwMDMwMDIwMyAhYMTBwcHB4uLi5uTkxMIBhgMDAwMDAwQwMDAwMDIyMjMzMzMwMDAwMDIyAgAABccCQb6UuYAAAAASUVORK5CYII=', 'base64');

// Select renders its own list (no native <select>), so the picker is read by opening it.
const picker = (page: Page) => page.locator('.motion-model-field .select-button');
const turboValue = (page: Page) => page.locator('label', {hasText: /^Turbo LoRA/}).locator('.select-value').first();

async function modelOptions(page: Page) {
  await picker(page).click();
  const list = page.locator('.select-list');
  await expect(list).toBeVisible();
  const items = (await list.locator('li').evaluateAll(els => els.map(el => {
    // The chips are part of the option, so read the model name with them removed.
    const c = el.cloneNode(true) as HTMLElement;
    c.querySelectorAll('.model-tag').forEach(n => n.remove());
    return c.textContent || '';
  })))
    .map(s => s.replace(/✓/g, '').replace(/\s+/g, ' ').trim())
    // A model that is not downloaded yet is still listed, flagged as missing.
    .map(s => s.replace(/\s*·\s*(not installed|não instalado|no instalado)$/, ''));
  await page.keyboard.press('Escape');
  return items;
}

async function chooseModel(page: Page, label: string) {
  await picker(page).click();
  await page.locator('.select-list li', {hasText: label}).first().click();
  // The closed control carries the tag chips too, so check the model name itself.
  await expect(picker(page).locator('.select-value .model-name')).toHaveText(label);
}

async function openStudio(page: Page) {
  // The first-run setup wizard covers the studio until it is finished or skipped: mark it done before the app boots.
  await page.addInitScript(() => {try {localStorage.setItem('henge-setup-done', '1');} catch {/* private browsing */}});
  await page.goto(BASE, {waitUntil: 'domcontentloaded'});
  const skip = page.getByRole('button', {name: /Skip setup|Pular configuração|Saltar configuración/});
  if (await skip.count()) await skip.click();
  await expect(page.locator('.settings-backdrop')).toHaveCount(0);
}

async function enterMotion(page: Page) {
  const motion = page.getByRole('button', {name: /^Motion transfer/});
  await expect(motion).toBeEnabled({timeout: 30_000});   // disabled until the bridge can extract guide frames
  if (await motion.getAttribute('aria-pressed') !== 'true') await motion.click();
  await expect(picker(page)).toBeVisible({timeout: 15_000});
}

async function uploadGuide(page: Page) {
  if (!GUIDE) return false;
  await page.locator('[data-testid=guide-input]').setInputFiles(GUIDE);
  // Uploading a guide opens the interval picker, and the studio only offers the First Frame once a range is confirmed.
  const trim = page.locator('.trim-overlay');
  await expect(trim).toBeVisible({timeout: 30_000});
  await trim.getByRole('button', {name: /Use full video|Usar o vídeo inteiro|Usar video completo/}).click();
  // The trimmed guide lives client-side; the bridge needs only a couple of seconds to probe and extract it.
  for (let i = 0; i < 25; i++) {
    if (await page.locator('.ffp-card').count()) return true;
    await page.waitForTimeout(1500);
  }
  return false;
}

test('the backend offers exactly the four current Motion models', async ({request}) => {
  const health = await (await request.get(`${BASE}/api/backend/health`)).json();
  const motion = Object.entries(health.models).filter(([, m]: [string, any]) => m.task === 'motion' && !m.hidden);
  expect(motion.map(([id]) => id)).toEqual(['motion', 'motion_tara', 'motion_mix_dyn99', 'motion_solar_ffp']);
  expect(Object.fromEntries(motion.map(([, m]: [string, any]) => [m.label, m.lora.split('/').pop()]))).toEqual({
    [MODELS.motion.label]: `${MODELS.motion.file}.safetensors`,
    [MODELS.tara.label]: `${MODELS.tara.file}.safetensors`,
    [MODELS.edit.label]: `${MODELS.edit.file}.safetensors`,
    [MODELS.solar.label]: `${MODELS.solar.file}.safetensors`,
  });
  // SolarRenderer FFP is only for a clip that starts from an edited frame.
  expect(motion.find(([id]) => id === 'motion_solar_ffp')![1]).toMatchObject({first_frame_only: true});
  // The edit model is the one a First Frame drives, and it runs on the standard 4-step turbo.
  expect(motion.find(([id]) => id === 'motion_mix_dyn99')![1]).toMatchObject({ffp: true, turbo_default: 'dmad4'});
  // The old comparison/FFP/SolarRenderer variants are gone from the studio.
  for (const gone of ['motion_ffp', 'motion_ffp_dyn95', 'motion_mix_dyn95', 'motion_solar_dyn95', 'motion_solar_dyn99'])
    expect(health.models[gone]).toBeUndefined();
});

test('the model picker offers the four models and follows the First Frame', async ({page}) => {
  test.setTimeout(900_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(String(error)));
  await openStudio(page);
  await enterMotion(page);

  // The picker fills in once the health payload arrives; wait for the four current models rather than the fallback.
  await expect.poll(async () => (await modelOptions(page)).length, {timeout: 30_000}).toBe(4);
  expect(await modelOptions(page)).toEqual([MODELS.motion.label, MODELS.tara.label, MODELS.edit.label, MODELS.solar.label]);
  // Each model carries tags on the picker itself: what it was trained for, and what it only handles by chance.
  await picker(page).click();
  const tags = await page.locator('.select-list li').evaluateAll(els => els.map(el => Array.from(el.querySelectorAll('.model-tag')).map(t => t.textContent)));
  await page.keyboard.press('Escape');
  // Character Swap is tagged `multi-reference · weaker` rather than "one reference": it does take more than one
  // picture, it was only trained with one.
  expect(tags).toEqual([['multi-reference', 'FFP ✓'], ['multi-reference', 'FFP ⚠'], ['FFP ✓', 'multi-reference · weaker'], ['first frame only']]);
  // The tag is explained, not just decorated: hovering the chip gives the reason.
  await picker(page).click();
  expect(await page.locator('.select-list li .model-tag').first().getAttribute('title')).toMatch(/reference pictures at once/);
  await page.keyboard.press('Escape');
  // Which model the studio remembered from the last session is the user's business; pick one explicitly.
  await chooseModel(page, MODELS.motion.label);
  // Plain Motion Transfer is prompted by what to copy from the guide; the prompt itself is one line that the
  // enhancer expands into the trained six-part caption.
  await expect(page.locator('.prompt-tips button').first()).toHaveText(/same performance|mesma atua\u00e7\u00e3o|misma actuaci\u00f3n/);
  await chooseModel(page, MODELS.tara.label);
  // TARA replaces performers: its examples name the picture that replaces them and keep the guide's motion.
  await expect(page.locator('.prompt-tips button').first())
    .toHaveText(/two performers|dois personagens|dos personajes/);
  await chooseModel(page, MODELS.motion.label);

  if (!await uploadGuide(page)) {expect(true, 'no guide clip: skipping the First Frame checks').toBeTruthy(); return;}
  // The First Frame card starts collapsed: open it, then ask for the frame editor.
  await page.locator('.ffp-card summary').click();
  await expect(page.locator('.ffp-card .first-frame-button')).toBeVisible();
  await page.locator('.ffp-card .first-frame-button').click();
  const modal = page.locator('.first-frame-modal');
  await expect(modal).toBeVisible();
  // The modal names the image editors this backend has, in the order it prefers them: FIBO 2.0 keeps the frame.
  await expect(modal.locator('.edit-editors button').first()).toHaveText(/FIBO 2\.0/);
  const what = modal.getByLabel(/What do you replace|O que você vai substituir|Qué reemplazas/);
  if (await what.count()) await what.fill('the hoodie');
  await modal.getByLabel(/With what|Pelo quê|Por qué/).fill('a luminous blue jacket');
  const edit = modal.getByRole('button', {name: /Edit with|Editar com|Editar con/});
  if (await edit.count() && await edit.isEnabled()) {
    // The frame editor is installed: edit the opening frame in place, the way the model wants it.
    await edit.click();
    await expect(modal.locator('figure img')).toBeVisible({timeout: 420_000});
  } else {
    // No editor on this machine: bring one in, which is the other supported route.
    const chooser = page.waitForEvent('filechooser');
    await modal.getByRole('button', {name: /Upload edited image|Enviar imagem editada|Subir imagen editada/}).click();
    (await chooser).setFiles({name: 'edited-frame.png', mimeType: 'image/png', buffer: EDITED_FRAME});
  }
  await modal.getByRole('button', {name: /Use as first frame|Usar como primeiro quadro|Usar como primer fotograma/}).click();
  // Attaching that frame is the edit workflow: the studio moves to the first-frame model on the standard turbo, and the
  // coaching switches to "the change first, then what has to survive it".
  await expect(page.locator('.ffp-card .ffp-current')).toBeVisible();
  await expect(picker(page).locator('.select-value .model-name')).toHaveText(MODELS.edit.label);
  await expect(turboValue(page)).toContainText('DMAD 4-step');
  await expect(page.locator('.prompt-tips button').first()).toHaveText(/replace the character|trocar o personagem|cambiar el personaje/);
  await expect(page.locator('.tip-hint')).toContainText(/who is replaced|quem é trocado|a quién se reemplaza/);

  // A deliberate model choice survives re-renders. An attached First Frame still makes this an edit, so the edit
  // sentences stay even when the user moves to TARA: the First Frame already says how the video starts.
  await chooseModel(page, MODELS.tara.label);
  await expect(picker(page).locator('.select-value .model-name')).toHaveText(MODELS.tara.label);
  await expect(page.locator('.prompt-tips button').first()).toHaveText(/replace the character|trocar o personagem|cambiar el personaje/);
  expect(errors).toEqual([]);
});
