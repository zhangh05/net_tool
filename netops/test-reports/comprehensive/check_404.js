const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const notFound = [];
  page.on('response', res => {
    if (res.status() === 404) notFound.push(res.url());
  });
  
  await page.goto('http://192.168.32.72:6133/test-humanize', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(5000);
  
  console.log('404 resources:', notFound);
  await browser.close();
}

test().catch(console.error);
