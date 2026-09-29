const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.argv[2] || 'playwright');

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://localhost:8000');
    await page.locator('#referenceInput').fill('Mechanical Ventilation to Minimize Progression of Lung Injury in Acute Respiratory Failure\nLei federal 12503/2011\nLei Federal n⁰ 9882/1999');
    await page.locator('#btnFormat').click();
    await page.locator('#resultsSection:not(.hidden)').waitFor({ timeout: 180000 });
    const text = await page.locator('#compList').innerText();
    assert(text.includes('v. 195, n. 4, p. 438-442'), 'Article title must resolve complete issue metadata');
    assert(text.includes('[New York, NY]'), 'Historical journal place must be present');
    assert(text.includes('Lei nº 12.503, de 11 de outubro de 2011'), 'Law signature date must be retained');
    assert(text.includes('Presidência da República'), 'Planalto source must use the presidency imprint');
    assert(text.includes('Rodovia Joaquim Pinto Lapa'), 'Law ementa must be present');
    assert(text.includes('Lei nº 9.882, de 3 de dezembro de 1999'), 'Superscript zero must not become law zero');
    assert(text.includes('https://www.planalto.gov.br/ccivil_03/leis/l9882.htm'), 'Older law must link to its Planalto page');
    fs.mkdirSync('artifacts/title-legal-verification', { recursive: true });
    for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.evaluate(() => {
        document.documentElement.style.scrollBehavior = 'auto';
        document.querySelector('#resultsSection').scrollIntoView();
      });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Horizontal overflow');
      await page.screenshot({ path: `artifacts/title-legal-verification/${name}.png`, animations: 'disabled' });
    }
    assert.deepEqual(errors, []);
    console.log('Title/legal UI: real API, article title, Planalto law, desktop/mobile layout OK');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
