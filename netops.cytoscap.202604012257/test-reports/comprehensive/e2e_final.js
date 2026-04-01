const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const chatResponses = [];
  page.on('response', res => {
    if (res.url().includes('session') || res.url().includes('chat/send')) {
      chatResponses.push({ status: res.status(), url: res.url().split('/').slice(-3).join('/') });
    }
  });
  
  try {
    console.log('Loading page...');
    await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForFunction(() => window.currentSessionId !== null, { timeout: 10000 });
    console.log('Session:', await page.evaluate(() => window.currentSessionId));
    
    // Toggle and open chat
    await page.click('#chatToggle');
    await page.waitForTimeout(1500);
    
    // Check elements
    const input = await page.$('#chatInput');
    console.log('Chat input found:', !!input);
    const msgsContainer = await page.$('#chatMessages');
    console.log('Messages container found:', !!msgsContainer);
    
    // Fill message
    await page.fill('#chatInput', '路由器和交换机的区别是什么？');
    await page.waitForTimeout(500);
    
    // Send via keyboard Enter
    await page.keyboard.press('Enter');
    console.log('Message sent');
    
    // Wait for AI response (up to 60s)
    let aiCame = false;
    for (let i = 0; i < 120; i++) {
      await page.waitForTimeout(500);
      // Check for chat-msg bubbles (the correct selector!)
      const bubbles = await page.$$('.chat-msg');
      if (bubbles.length >= 2) {
        aiCame = true;
        console.log(`✅ AI response arrived after ${(i+1)*0.5}s! Messages: ${bubbles.length}`);
        for (const b of bubbles.slice(-2)) {
          const t = await b.innerText();
          console.log(`  [${t.slice(0, 60)}]`);
        }
        
        // Check for ops card
        const opsCard = await page.$('.chat-ops-card');
        console.log(`  Ops card: ${!!opsCard}`);
        
        // Check typing indicator is gone
        const typing = await page.$('#chat-typing');
        console.log(`  Typing indicator: ${!!typing}`);
        break;
      }
    }
    
    if (!aiCame) {
      console.log('❌ AI response did not arrive within 60s');
      console.log('Chat responses:', chatResponses.slice(-5));
    }
    
  } catch(e) {
    console.log('ERROR:', e.message);
  } finally {
    await browser.close();
  }
}

test().catch(console.error);
