const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.argv[2] || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    fs.mkdirSync('artifacts', { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const reference = '10.36416/1806-3756/e20200590\n9788535208031';
    await page.goto('http://localhost:8000');
    await page.locator('#referenceInput').fill(reference);
    await page.locator('#btnFormat').click();
    await page.locator('#resultsSection:not(.hidden)').waitFor({ timeout: 60000 });
    const results = await page.locator('#compList').innerText();
    assert(results.includes('10.36416/1806-3756/e20200590'));
    assert(results.includes('Revisão necessária'));
    assert(results.includes('Conferida nas fontes'));
    assert(results.includes('ELMO 1.0'));
    assert(results.includes('v. 47, n. 3, e20200590, May/June 2021'));
    assert(results.includes('[Bras\u00edlia, DF], v. 47'));
    assert(results.includes('Acesso em:'));
    assert(results.includes('Fonte: Crossref'));
    assert(results.includes('Fonte: NLM Catalog'));
    await page.evaluate(() => { document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, 0); });
    await page.screenshot({ path: 'artifacts/corretor-desktop.png', fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: 'artifacts/corretor-mobile.png', fullPage: true });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    assert(!overflow, 'Mobile layout must not overflow horizontally');
    assert.deepEqual(errors, []);
    console.log('Corretor desktop/mobile: DOI, warnings, sources, layout and JavaScript OK');

    const credentials = Object.fromEntries(fs.readFileSync('hermes-dashboard.local.env', 'utf8')
      .trim().split(/\r?\n/).filter(line => line.includes('=')).map(line => {
        const split = line.indexOf('='); return [line.slice(0, split), line.slice(split + 1)];
      }));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto('http://localhost:9119');
    await page.locator('input[name="username"]').fill(credentials.HERMES_DASHBOARD_BASIC_AUTH_USERNAME);
    await page.locator('input[name="password"]').fill(credentials.HERMES_DASHBOARD_BASIC_AUTH_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.locator('input[name="password"]').waitFor({ state: 'hidden', timeout: 30000 });
    await page.waitForFunction(() => (document.body?.innerText || '').trim().length > 100, null, { timeout: 30000 });
    await page.screenshot({ path: 'artifacts/hermes-dashboard.png', fullPage: true });
    console.log('Hermes page:', await page.title());
    console.log('Hermes dashboard: authenticated login OK');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
