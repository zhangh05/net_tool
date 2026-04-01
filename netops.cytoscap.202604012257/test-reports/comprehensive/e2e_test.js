const { chromium } = require('playwright');

async function test(name, url, messages) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  const network404 = [];
  
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  page.on('response', res => { if (res.status() === 404) network404.push(res.url()); });
  
  try {
    console.log(`\n=== ${name} ===`);
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(1000);
    
    // Toggle chat
    const chatToggle = await page.$('#chatToggle');
    if (chatToggle) await chatToggle.click();
    await page.waitForTimeout(500);
    
    for (const msg of messages) {
      console.log(`  Sending: "${msg.slice(0, 40)}..."`);
      const input = await page.$('#chatInput');
      if (input) {
        await input.fill(msg);
        await page.waitForTimeout(300);
        const sendBtn = await page.$('.chat-send-btn');
        if (sendBtn) await sendBtn.click();
        await page.waitForTimeout(15000); // Wait for AI response
        
        // Check for ops card
        const opsCard = await page.$('.chat-ops-card');
        if (opsCard) {
          console.log(`  ✅ Ops card appeared`);
          // Try to execute
          const execBtn = await page.$('.chat-ops-execute, .ops-execute');
          if (execBtn) {
            await execBtn.click();
            await page.waitForTimeout(2000);
            console.log(`  ✅ Execute clicked`);
          }
        } else {
          console.log(`  ⚠️ No ops card`);
        }
        
        // Count bubbles
        const bubbles = await page.$$('.chat-bubble');
        console.log(`  Chat bubbles: ${bubbles.length}`);
      }
    }
    
    if (errors.length) console.log('  JS Errors:', errors.slice(0, 3));
    if (network404.length) console.log('  404:', network404.slice(0, 3));
    else console.log('  No 404s ✅');
    
  } finally {
    await browser.close();
  }
}

(async () => {
  await test('小办公室拓扑', 'http://192.168.32.72:6133/test-small', [
    '添加一台核心路由器，再加一台接入交换机，PC接交换机'
  ]);
  await test('中等规模拓扑', 'http://192.168.32.72:6133/test-medium', [
    '帮我在当前拓扑添加8台PC，分两组，每组4台，每组接一台接入交换机'
  ]);
  await test('知识问答', 'http://192.168.32.72:6133/test-humanize', [
    '路由器和交换机的区别是什么？'
  ]);
  console.log('\n=== All E2E tests done ===');
})().catch(e => console.error('Fatal:', e.message));
