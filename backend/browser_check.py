"""UI smoke check while training owns the GPU; this never queues a render."""
import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright

root=Path(__file__).parent/'evidence';root.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser=p.firefox.launch(headless=True,executable_path='/root/.cache/ms-playwright/firefox-1490/firefox/firefox')
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8188',wait_until='networkidle')
    page.get_by_role('button',name='EN',exact=True).click()
    page.get_by_test_id('guide-input').set_input_files('/data/datasets/openjutsu/color_binding_v2_30/train/animate/targets/000151.mp4')
    page.get_by_role('button',name='Confirm interval →').click()
    page.get_by_test_id('picture-input').set_input_files('/data/datasets/openjutsu/color_binding_v2_30/train/animate/refs_1/000151.webp')
    page.get_by_role('textbox',name='Execution prompt',exact=True).fill('motion_transfer: Animate @Picture1 with the performance in @Video1.')
    with page.expect_response(lambda r:r.url.endswith('/api/backend/jobs') and r.request.method=='POST') as response:
        page.get_by_role('button',name='Upload and plan',exact=True).click()
    created=response.value.json();assert response.value.ok,created
    jid=created['id'];job=created
    try:
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            job=page.request.get(f'http://127.0.0.1:8188/api/backend/jobs/{jid}').json()
            if job['status']=='waiting_gpu':break
            page.wait_for_timeout(500)
        assert job['status']=='waiting_gpu',job
        page.locator('.generation-jobs select').select_option(jid)
        panel=page.get_by_label('Generation backend',exact=True)
        panel.get_by_text('Waiting for the active H3 training to release the GPU.',exact=True).wait_for(timeout=10000)
        page.screenshot(path=str(root/'kagemane-connected.png'),full_page=True)
        page.get_by_role('button',name='Cancel job',exact=True).click()
        panel.get_by_text('Cancelled by user',exact=True).wait_for(timeout=10000)
        result=dict(upload_plan_click='passed',training_gpu_guard=job['status'],cancel_click='passed',browser_errors=errors,job_id=jid)
        (root/'browser_check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert not errors
    finally:
        state=page.request.get(f'http://127.0.0.1:8188/api/backend/jobs/{jid}').json()
        if state['status'] not in ['completed','failed','cancelled']:
            page.request.post(f'http://127.0.0.1:8188/api/backend/jobs/{jid}/cancel')
        browser.close()
