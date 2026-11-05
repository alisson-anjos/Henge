import {expect, test} from '@playwright/test';
/** "Continue with…" on the missing-models checklist is remembered; Settings → Models shows it again. HENGE_E2E_BASE overrides the address. */
test('the missing-models checklist shows once, then only from Settings', async ({page}) => {
  await page.addInitScript(() => {try {localStorage.setItem('henge-setup-done', '1');} catch {}});
  await page.goto(process.env.HENGE_E2E_BASE || 'http://127.0.0.1:8188');
  const go = page.getByRole('button', {name: /^Continue with/}).first();
  await expect(go).toBeVisible({timeout: 20_000}); await go.click();
  await expect(page.locator('.setup-screen')).toHaveCount(0);
  await page.reload(); await page.waitForTimeout(5000);
  await expect(page.locator('.setup-screen')).toHaveCount(0);
  await page.getByRole('button', {name: 'Settings', exact: true}).first().click();
  await page.locator('.settings-tabs button', {hasText: 'Models'}).click();
  await page.getByRole('button', {name: 'Show the model checklist'}).click();
  await expect(page.locator('.settings-center')).toHaveCount(0);
  await expect(page.locator('.setup-screen')).toBeVisible({timeout: 10_000});
  await page.screenshot({path: 'test-results/checklist-again.png'});
});
