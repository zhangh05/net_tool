const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const networkErrors = [];
  const consoleLogs = [];
  page.on('console', msg => {
    consoleLogs.push(`[${msg.type()}] ${msg.text().slice(0, 150)}`);
  });
  page.on('response', res => {
    if (res.status() >= 400) networkErrors.push(`${res.status()} ${res.url().slice(0,80)}`);
  });
  
  try {
    await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 20000 });
    
    // Wait for sessions to load
    await page.waitForFunction(() => window.currentSessionId !== null, { timeout: 10000 });
    console.log('Session initialized:', await page.evaluate(() => window.currentSessionId));
    
    // Toggle chat
    await page.click('#chatToggle');
    await page.waitForTimeout(1000);
    
    // Type in chat
    await page.fill('#chatInput', '路由器和交换机的区别是什么？');
    await page.waitForTimeout(300);
    
    // Call sendChat
    const result = await page.evaluate(async () => {
      sendChat();
      return 'sendChat called';
    });
    console.log(result);
    
    // Wait for response (up to 30s)
    await page.waitForFunction(() => {
      const bubbles = document.querySelectorAll('.chat-bubble');
      return bubbles.length >= 2; // user + ai
    }, { timeout: 30000 });
    
    const bubbles = await page.$$('.chat-bubble');
    console.log('Bubbles:', bubbles.length);
    
    // Get bubble content
    for (let i = 0; i < bubbles.length; i++) {
      const text = await bubbles[i].innerText();
      console.log(`Bubble ${i}: ${text.slice(0, 100)}`);
    }
    
    if (networkErrors.length) console.log('Network errors:', networkErrors);
    const errorLogs = consoleLogs.filter(l => l.includes('[error]'));
    if (errorLogs.length) console.log('JS Errors:', errorLogs.slice(0, 3));
    
  } catch(e) {
    console.log('ERROR:', e.message);
    if (networkErrors.length) console.log('Network errors:', networkErrors);
    console.log('Recent console:', consoleLogs.slice(-5));
  } finally {
    await browser.close();
  }
}

test().catch(console.error);
