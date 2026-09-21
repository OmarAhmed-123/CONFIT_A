"""Optional Playwright harness. Provision an isolated local brand account first.
Install: pip install playwright && python -m playwright install --with-deps chromium
The production/runtime dependency manifests intentionally do not include Playwright.
"""
import json, re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import argparse
from urllib.parse import urlsplit
parser = argparse.ArgumentParser(description='Mutating LOCAL-ONLY partner browser smoke; never use production accounts')
parser.add_argument('--base-url', default='http://127.0.0.1:43123')
parser.add_argument('--credentials-file', required=True, help='Local JSON containing email/password; keep outside Git')
parser.add_argument('--evidence-dir', required=True)
args = parser.parse_args()
base = args.base_url.rstrip('/')
if urlsplit(base).hostname not in ('localhost', '127.0.0.1'):
    parser.error('Only loopback test servers are permitted')
evidence = Path(args.evidence_dir)
evidence.mkdir(parents=True, exist_ok=True)
results=[]
def record(name):
    results.append({'test':name,'status':'passed'})
    print('PASS', name, flush=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True, args=['--no-sandbox'])
    context=browser.new_context(viewport={'width':1440,'height':1000})
    login=context.request.post(base+'/api/v1/auth/login',data=json.load(open(args.credentials_file)))
    assert login.status==200, login.status
    user=login.json()['user']
    context.add_init_script('localStorage.setItem("confit_user", '+json.dumps(json.dumps(user))+');')
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.goto(base+'/b2b')
    expect(page.get_by_text('LOCAL TEST — Not production Command Center')).to_be_visible(timeout=20000)
    expect(page.get_by_text('Brand Partner — verification pending',exact=True)).to_be_visible()
    record('Real cookie login -> brand dashboard; unverified badge is truthful')
    page.goto(base+'/b2b/catalog')
    page.get_by_role('button',name=re.compile('Upload CSV|Bulk')).first.click()
    content='title,category_slug,base_price,color_family,thumbnail_url,sku_code,size,color,stock_level\nمعطف اختبار,coats,19.99,Navy,https://example.com/coat.jpg,E2E-COAT,M,Navy,10\n'
    page.locator('input[type=file]').set_input_files({'name':'smoke.csv','mimeType':'text/csv','buffer':content.encode()})
    expect(page.get_by_text('E2E-COAT',exact=True)).to_be_visible(timeout=20000)
    if page.get_by_role('dialog',name='Import catalog').is_visible(): page.get_by_role('dialog').get_by_role('button',name='Cancel').click()
    record('CSV upload -> persisted Arabic product/SKU via real API')
    page.get_by_text('Edit Stock',exact=True).click()
    page.get_by_label('Stock for E2E-COAT').fill('12')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.get_by_text('12 units',exact=True)).to_be_visible(timeout=20000)
    record('SKU warehouse stock edit -> refreshed persisted value')
    page.goto(base+'/b2b/inventory')
    page.get_by_role('button',name='+ Add Store',exact=True).click()
    for field,value in [('name','متجر الجيزة التجريبي'),('city','Giza'),('country','EG'),('address','Local test only')]:
        page.get_by_label('Store '+field,exact=True).fill(value)
    page.get_by_role('button',name='Create Store',exact=True).click()
    expect(page.get_by_text('متجر الجيزة التجريبي',exact=True).first).to_be_visible(timeout=20000)
    page.get_by_label('Inventory store').select_option(label='متجر الجيزة التجريبي')
    page.get_by_label('Inventory SKU').select_option(index=1)
    page.get_by_label('Store on-hand quantity').fill('7')
    page.get_by_role('button',name='Save store stock',exact=True).click()
    expect(page.get_by_text('Store inventory saved. Warehouse stock was not changed.',exact=True)).to_be_visible(timeout=20000)
    record('Store create -> store stock upsert -> availability rendered')
    page.screenshot(path=str(evidence/'local-inventory.png'),full_page=True)
    page.goto(base+'/b2b/placements')
    page.get_by_role('button',name='Create Placement',exact=True).click()
    page.get_by_role('button',name='Save placement',exact=True).click()
    expect(page.get_by_role('button',name='Pause placement')).to_be_visible(timeout=20000)
    page.get_by_role('button',name='Pause placement').click()
    expect(page.get_by_role('button',name='Resume placement')).to_be_visible(timeout=20000)
    record('Placement create -> pause -> persisted status (not ad-delivery verification)')
    page.goto(base+'/b2b/analytics')
    expect(page.get_by_text('Commerce activity snapshot — not a linked-session funnel')).to_be_visible(timeout=20000)
    expect(page.get_by_text('Not enough data',exact=True).first).to_be_visible()
    record('Analytics loads with explicit unknown cohort instead of benchmark')
    page.screenshot(path=str(evidence/'local-analytics.png'),full_page=True)
    assert not errors, errors
    record('No uncaught browser JavaScript errors during tested workflow')
    browser.close()
(evidence/'browser-smoke.json').write_text(json.dumps({'environment':'isolated local PostgreSQL + Vite + FastAPI; NOT production','checks':results},ensure_ascii=False,indent=2))
