import {expect, test} from '@playwright/test';
/** The assistant's settings scroll inside the panel down to GPT Image and Save, on desktop and phone. HENGE_E2E_BASE overrides the address. */
for (const vp of [{width: 1280, height: 720}, {width: 390, height: 760}]) {
  test(`assistant settings scroll to GPT Image ${vp.width}`, async ({page}) => {
    await page.setViewportSize(vp);
    await page.addInitScript(() => {try {localStorage.setItem('henge-setup-done', '1');} catch {}});
    await page.goto(process.env.HENGE_E2E_BASE || 'http://127.0.0.1:8188');
    const skip = page.getByRole('button', {name: /Skip setup|Pular configuração/}); if (await skip.count()) await skip.click();
    const go = page.getByRole('button', {name: /^Continue with/}).first();
    await go.waitFor({state: 'visible', timeout: 15_000}).then(() => go.click(), () => undefined);
    await page.locator('.assistant-fab').click();
    await page.locator('.assistant-settings-button').click();
    const box = page.locator('.assistant-settings'); await expect(box).toBeVisible();
    const toggle = page.locator('#gpt-image-on');
    await toggle.scrollIntoViewIfNeeded(); await expect(toggle).toBeInViewport();
    if ((await toggle.getAttribute('aria-checked')) !== 'true') await toggle.click();
    const save = page.locator('.assistant-settings .plan-actions .primary');
    await box.evaluate(e => e.scrollTo(0, e.scrollHeight));
    await expect(save).toBeInViewport();
    expect(await box.evaluate(e => e.scrollHeight > e.clientHeight)).toBeTruthy();
    await page.waitForTimeout(400); await toggle.scrollIntoViewIfNeeded(); await toggle.screenshot({path: `test-results/toggle-${vp.width}.png`});
    await page.screenshot({path: `test-results/assistant-scroll-${vp.width}.png`});
  });
}
