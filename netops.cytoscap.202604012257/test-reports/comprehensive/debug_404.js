const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  page.on('response', res => {
    if (res.status() >= 400) console.log(`${res.status()} ${res.url().replace('http://192.168.32.72:6133','')}`);
  });
  
  await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(3000);
  
  console.log('Done');
  await browser.close();
}

test().catch(console.error);
