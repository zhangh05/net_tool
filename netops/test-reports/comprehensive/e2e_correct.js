const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    console.log('Loading page...');
    await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForFunction(() => window.currentSessionId !== null, { timeout: 10000 });
    console.log('Session:', await page.evaluate(() => window.currentSessionId));
    
    // Toggle chat
    await page.click('#chatToggle');
    await page.waitForTimeout(1500);
    
    // Test 1: Knowledge question
    console.log('\n=== Test 1: Knowledge Question ===');
    await page.fill('#chatInput', '路由器和交换机的区别是什么？');
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    
    // Wait for complete AI response
    let done = false;
    for (let i = 0; i < 120; i++) {
      await page.waitForTimeout(500);
      const typing = await page.$('#chat-typing');
      if (!typing) {
        done = true;
        break;
      }
    }
    
    if (done) {
      const bubbles = await page.$$('.chat-msg');
      console.log(`✅ Response complete! Messages: ${bubbles.length}`);
      for (const b of bubbles.slice(-2)) {
        const t = await b.innerText();
        console.log(`  - ${t.slice(0, 100)}`);
      }
    } else {
      console.log('❌ Response not complete in 60s');
    }
    
    // Test 2: Topology creation
    console.log('\n=== Test 2: Topology Creation ===');
    await page.fill('#chatInput', '添加一台核心路由器，再加一台接入交换机，PC接交换机');
    await page.waitForTimeout(300);
    await page.keyboard.press('Enter');
    
    done = false;
    for (let i = 0; i < 120; i++) {
      await page.waitForTimeout(500);
      const typing = await page.$('#chat-typing');
      if (!typing) {
        done = true;
        break;
      }
    }
    
    if (done) {
      const bubbles = await page.$$('.chat-msg');
      const opsCard = await page.$('.chat-ops-card');
      console.log(`✅ Response complete! Messages: ${bubbles.length}, Ops card: ${!!opsCard}`);
      if (opsCard) {
        const execBtn = await opsCard.$('.chat-ops-execute');
        console.log(`  Execute button: ${!!execBtn}`);
        if (execBtn) {
          await execBtn.click();
          await page.waitForTimeout(2000);
          const nodes = await page.evaluate(() => window.cy ? window.cy.nodes().length : -1);
          console.log(`  ✅ Topology nodes after execute: ${nodes}`);
        }
      }
    }
    
  } catch(e) {
    console.log('ERROR:', e.message);
  } finally {
    await browser.close();
  }
}

test().catch(console.error);
