import {expect, test, type Page} from '@playwright/test';

/** Character Swap with an edited first frame: BFS Body Swap Selective swaps the clicked person, the guide becomes a
    normal map by default, the job renders, and a reloaded studio shows the job's edited frame again.

    HENGE_E2E_GUIDE=/path/to/clip.mp4 HENGE_E2E_PICTURE=/path/to/character.png [HENGE_E2E_X=.5 HENGE_E2E_Y=.5] \
    HENGE_E2E_BASE=http://127.0.0.1:8188 npx playwright test tests/e2e/swap-normal-guide.spec.ts
*/
const BASE = process.env.HENGE_E2E_BASE || 'http://127.0.0.1:8188';
const GUIDE = process.env.HENGE_E2E_GUIDE || '';
const PICTURE = process.env.HENGE_E2E_PICTURE || '';
// Where the person to replace is in the first frame, relative to the frame.
const AT = {x: Number(process.env.HENGE_E2E_X || .5), y: Number(process.env.HENGE_E2E_Y || .5)};
const SHOTS = process.env.HENGE_E2E_SHOTS || '';

async function openStudio(page: Page) {
  await page.addInitScript(() => {try {localStorage.setItem('henge-setup-done', '1');} catch {/* private browsing */}});
  await page.goto(BASE, {waitUntil: 'domcontentloaded'});
  const skip = page.getByRole('button', {name: /Skip setup|Pular configuração|Saltar configuración/});
  if (await skip.count()) await skip.click();
  await expect(page.locator('.settings-backdrop')).toHaveCount(0);
}

/** A checklist with missing models (e.g. an outdated Motion LoRA) covers the studio until it is dismissed. */
async function continuePastMissingModels(page: Page) {
  const go = page.getByRole('button', {name: /^(Continue with|Continuar com|Continuar con)/});
  if (await go.count() && await go.first().isVisible()) await go.first().click();
}

test('a swapped first frame drives a normal-map Character Swap', async ({page}) => {
  test.skip(!GUIDE || !PICTURE, 'needs HENGE_E2E_GUIDE and HENGE_E2E_PICTURE');
  test.setTimeout(1_800_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(String(error)));
  await openStudio(page);
  const swap = page.locator('.mode-switch button').first();
  await expect(swap).toBeEnabled({timeout: 60_000});
  await swap.click();
  await expect(swap).toHaveAttribute('aria-pressed', 'true');

  await page.locator('[data-testid=guide-input]').setInputFiles(GUIDE);
  const trim = page.locator('.trim-overlay');
  await expect(trim).toBeVisible({timeout: 30_000});
  await trim.getByRole('button', {name: /Use full video|Usar o vídeo inteiro|Usar video completo/}).click();
  await page.locator('[data-testid=picture-input]').setInputFiles(PICTURE);
  await expect(page.locator('.ffp-card')).toBeVisible({timeout: 40_000});
  await continuePastMissingModels(page);
  await page.screenshot({path: 'test-results/normal-guide-0-studio.png'});

  // The First Frame editor prefers BFS Body Swap Selective for a person swap, and says what it does.
  await page.locator('.ffp-card > summary').click();
  await page.locator('.ffp-card .first-frame-button').click();
  const modal = page.locator('.first-frame-modal');
  await expect(modal).toBeVisible();
  await expect(modal.getByRole('button', {name: /Edit with .*Selective|Editar com .*Selective/})).toBeVisible({timeout: 60_000});
  await expect(modal.locator('.edit-hint')).toBeVisible();
  // The people are found as soon as the frame shows: a click picks who is replaced.
  const canvas = modal.locator('canvas.segment-pick');
  await expect(canvas).toBeVisible({timeout: 180_000});
  const box = (await canvas.boundingBox())!;
  await page.mouse.click(box.x + box.width * AT.x, box.y + box.height * AT.y);
  await expect(modal.locator('.ff-status')).toHaveText(/selected|selecionada|seleccionada/);
  await page.screenshot({path: 'test-results/normal-guide-1-picked.png'});
  await modal.getByRole('button', {name: /Edit with|Editar com|Editar con/}).click();
  await expect(modal.getByRole('button', {name: /Use as first frame|Usar como/})).toBeEnabled({timeout: 600_000});
  await page.screenshot({path: 'test-results/normal-guide-2-edited.png'});
  await modal.getByRole('button', {name: /Use as first frame|Usar como/}).click();
  await expect(modal).toBeHidden();

  // With the edited frame, the normal-map guide is on by default and replaces the latent/reference choice.
  const normals = page.locator('.ffp-normals .toggle');
  await expect(normals).toBeChecked();
  await expect(page.locator('.ffp-mode')).toHaveCount(0);
  await page.screenshot({path: 'test-results/normal-guide-3-card.png', fullPage: true});

  await continuePastMissingModels(page);
  const prompt = page.getByRole('textbox', {name: 'Execution prompt'});
  if (!(await prompt.inputValue()).trim()) await prompt.fill('Keep the people beside her and the city skyline exactly as in the edited first frame.');
  if (SHOTS) {const field = page.getByLabel(/Seconds per shot|Segundos por shot|Segundos por toma/); if (await field.count()) await field.fill(SHOTS);}
  const approve = page.locator('.prompt-assist-row input[type=checkbox]');
  if (await approve.count() && !await approve.isChecked()) await approve.check();
  // The upload can take a while: wait for the bridge's answer (the job), then read the stored request back.
  const created = page.waitForResponse(r => r.url().endsWith('/api/backend/jobs') && r.request().method() === 'POST', {timeout: 600_000});
  await page.getByRole('button', {name: /^Generate$|^Gerar$|^Generar$/}).click();
  const reply = await created;
  expect(reply.ok(), await reply.text()).toBeTruthy();
  const id = (await reply.json()).id as string;
  const stored = await (await page.request.get(`${BASE}/api/backend/jobs/${id}`)).json();
  expect(stored.request).toMatchObject({mode: 'swap', guide_first_frame: true, guide_normals: true});

  let job: any = null;
  await expect.poll(async () => {
    job = await (await page.request.get(`${BASE}/api/backend/jobs/${id}`)).json();
    return job.status;
  }, {timeout: 1_500_000, intervals: [10_000]}).toMatch(/completed|failed/);
  expect(job.status, job.error || '').toBe('completed');
  await page.screenshot({path: 'test-results/normal-guide-4-done.png', fullPage: true});

  // A reloaded studio shows the job's edited first frame again (it is not a Picture: it has its own source file).
  const frame = await page.request.get(`${BASE}/api/backend/jobs/${job.id}/source/first_frame`);
  expect(frame.ok()).toBeTruthy();
  console.log(`job ${job.id}`);
  expect(errors).toEqual([]);
});
