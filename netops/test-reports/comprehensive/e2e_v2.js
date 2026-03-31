const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
    if (msg.text().includes('[AI反馈]')) console.log('AI:', msg.text().slice(0, 100));
  });
  
  try {
    await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(5000); // Wait for sessions to load
    
    console.log('URL:', page.url());
    
    // Check session info
    const sessionInfo = await page.evaluate(() => ({
      projectId: window.currentProjectId,
      sessionId: window.currentSessionId,
      chatSending: typeof window.chatSending !== 'undefined' ? window.chatSending : 'UNDEFINED'
    }));
    console.log('Session:', sessionInfo);
    
    // Click chat toggle
    const toggle = await page.$('#chatToggle');
    if (toggle) {
      await toggle.click();
      await page.waitForTimeout(1000);
    }
    
    // Type message using keyboard events (more reliable)
    await page.focus('#chatInput');
    await page.waitForTimeout(300);
    await page.keyboard.type('添加一台核心路由器，再加一台接入交换机，PC接交换机', { delay: 50 });
    await page.waitForTimeout(500);
    
    // Find and click send button by evaluating JS
    const sent = await page.evaluate(() => {
      if (typeof sendChat === 'function') {
        sendChat();
        return true;
      }
      return false;
    });
    console.log('sendChat called:', sent);
    
    // Wait for AI response
    await page.waitForTimeout(20000);
    
    // Check results
    const results = await page.evaluate(() => {
      const bubbles = document.querySelectorAll('.chat-bubble, .message-content, .chat-msg-content');
      const opsCard = document.querySelector('.chat-ops-card, #topo-ops-card');
      return {
        bubbleCount: bubbles.length,
        hasOpsCard: !!opsCard,
        lastBubbleText: bubbles.length > 0 ? bubbles[bubbles.length-1].innerText.slice(0, 200) : 'none'
      };
    });
    console.log('Results:', results);
    
    if (errors.length) console.log('JS Errors:', errors.slice(0, 5));
    
  } finally {
    await browser.close();
  }
}

test().catch(e => console.error('Fatal:', e.message));
