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
    await page.locator('#referenceInput').fill('Dom Casmurro\nLei federal 11892/2008\nSenado Federal. PL 2338/2023');
    await page.locator('#btnFormat').click();
    await page.locator('#resultsSection:not(.hidden)').waitFor({ timeout: 180000 });
    const text = await page.locator('#compList').innerText();
    assert(text.includes('Candidato:'), 'Book title must expose candidates');
    assert(text.includes('Projeto de lei n. 2338'), 'Senate bill must be formatted');
    assert(text.includes('29 de dezembro de 2008'), 'Law signature date must be retained');
    assert(text.includes('secao e extensao completa'), 'Unverified publication details must be visible');
    assert(text.includes('nao a uma lei sancionada'), 'Bill must remain distinct from a law');
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
    console.log('Title/legal UI: real API, candidates, legal warnings, desktop/mobile layout OK');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
