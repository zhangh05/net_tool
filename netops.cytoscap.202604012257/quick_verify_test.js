const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  // Listen for console errors
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('response', response => {
    if (response.status() >= 500) {
      errors.push(`500 ERROR: ${response.url()} - ${response.status()}`);
    }
  });

  try {
    await page.goto('http://192.168.32.72:6133', { waitUntil: 'networkidle', timeout: 15000 });
    console.log('Page loaded OK');

    // Click on first project
    const projectCard = page.locator('.project-card, .card, [data-project], .item').first();
    if (await projectCard.count() > 0) {
      await projectCard.click();
      console.log('Entered project');
      await page.waitForTimeout(2000);
    } else {
      console.log('No project cards found, trying nav');
    }

    // Find chat input and send test message
    const inputs = page.locator('input[type="text"], textarea');
    const count = await inputs.count();
    console.log(`Found ${count} input fields`);

    if (count > 0) {
      await inputs.first().fill('添加路由器ID为R_test1');
      await inputs.first().press('Enter');
      console.log('Message sent');
      await page.waitForTimeout(3000);
    }

    // Report errors
    if (errors.length > 0) {
      console.log('ERRORS FOUND:');
      errors.forEach(e => console.log(' - ' + e));
    } else {
      console.log('NO ERRORS - Test PASSED');
    }

  } catch (e) {
    console.log('TEST ERROR: ' + e.message);
  }

  await browser.close();
})();
