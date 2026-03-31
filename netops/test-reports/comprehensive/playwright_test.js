const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  // Collect console errors
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  
  try {
    // Load the app
    await page.goto('http://192.168.32.72:6133/test-humanize', { waitUntil: 'networkidle', timeout: 15000 });
    console.log('Page loaded OK');
    
    // Check if chat panel exists
    const chatToggle = await page.$('#chatToggle');
    console.log('Chat toggle found:', !!chatToggle);
    
    // Click chat toggle
    if (chatToggle) {
      await chatToggle.click();
      await page.waitForTimeout(1000);
    }
    
    // Check if chat input exists
    const chatInput = await page.$('#chatInput');
    console.log('Chat input found:', !!chatInput);
    
    // Type a test message
    if (chatInput) {
      await chatInput.fill('帮我规划一个小办公室网络，3台PC，1台服务器');
      await page.waitForTimeout(500);
      
      // Find and click send button
      const sendBtn = await page.$('.chat-send-btn, #chatSendBtn, [class*="send"]');
      if (sendBtn) {
        await sendBtn.click();
        console.log('Message sent');
        
        // Wait for AI response (max 30s)
        await page.waitForTimeout(20000);
        
        // Check for chat bubbles
        const bubbles = await page.$$('.chat-bubble, .chat-msg, .message');
        console.log('Chat bubbles found:', bubbles.length);
        
        // Check for ops card
        const opsCard = await page.$('.chat-ops-card, #topo-ops-card, [class*="ops-card"]');
        console.log('Ops card found:', !!opsCard);
        
        // Get page title
        const title = await page.title();
        console.log('Page title:', title);
        
        // Check for any ops buttons
        const execBtns = await page.$$('[class*="execute"], .chat-ops-execute');
        console.log('Execute buttons:', execBtns.length);
      } else {
        console.log('Send button not found');
      }
    }
    
    // Report errors
    if (errors.length > 0) {
      console.log('Console errors:', errors.slice(0, 5));
    } else {
      console.log('No console errors');
    }
    
  } catch(e) {
    console.log('Error:', e.message);
  } finally {
    await browser.close();
  }
}

test();
