import json,time
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('/data/OpenJutsu/backend/evidence');root.mkdir(exist_ok=True)
with sync_playwright() as p:
 browser=p.firefox.launch(headless=True,executable_path='/root/.cache/ms-playwright/firefox-1490/firefox/firefox')
 page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8188',wait_until='networkidle');page.get_by_role('button',name='EN',exact=True).click();page.get_by_test_id('guide-input').set_input_files('/data/datasets/openjutsu/color_binding_v2_30/train/animate/targets/000151.mp4');page.get_by_role('button',name='Confirm interval →').click();page.get_by_test_id('picture-input').set_input_files('/data/datasets/openjutsu/color_binding_v2_30/train/animate/refs_1/000151.webp');page.get_by_role('textbox',name='Execution prompt',exact=True).fill('motion_transfer: Animate @Picture1 with the performance in @Video1.');page.get_by_role('button',name='Upload and plan',exact=True).wait_for(state='visible');page.get_by_role('button',name='Upload and plan',exact=True).click();page.get_by_text('Waiting for the active H3 training to release the GPU.',exact=True).wait_for(timeout=20000)
 page.screenshot(path=str(root/'kagemane-connected.png'),full_page=True)
 jobs=page.request.get('http://127.0.0.1:8188/api/backend/jobs').json();test=jobs[0];assert test['status']=='waiting_gpu',test
 page.get_by_role('button',name='Cancel job',exact=True).click();page.get_by_text('Cancelled by user',exact=True).wait_for(timeout=10000)
 result={'upload_plan_click':'passed','training_gpu_guard':test['status'],'cancel_click':'passed','browser_errors':errors,'job_id':test['id']};(root/'browser_check.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));assert not errors
 browser.close()
