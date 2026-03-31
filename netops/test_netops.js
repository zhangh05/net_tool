const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });
  
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });
  
  console.log('Navigating to http://192.168.32.72:6133...');
  await page.goto('http://192.168.32.72:6133', { timeout: 30000 });
  await page.waitForTimeout(3000);
  
  // Take initial screenshot
  await page.screenshot({ path: '/root/netops/test_feedback.png', fullPage: false });
  console.log('Screenshot saved to /root/netops/test_feedback.png');
  
  // Get page content to understand the UI
  const title = await page.title();
  console.log('Page title:', title);
  
  // Look for project list
  const bodyText = await page.textContent('body');
  console.log('Page content preview:', bodyText.substring(0, 500));
  
  await browser.close();
  console.log('Done');
})().catch(err => {
  console.error('Error:', err.message);
  process.exit(1);
});
