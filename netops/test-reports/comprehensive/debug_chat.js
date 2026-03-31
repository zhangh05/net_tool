const { chromium } = require('playwright');

async function test() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  page.on('console', msg => console.log('BROWSER:', msg.type(), msg.text().slice(0, 100)));
  page.on('response', res => {
    if (res.status() >= 400) console.log('HTTP', res.status(), res.url().replace('http://192.168.32.72:6133', ''));
  });
  
  try {
    // Try main page first
    console.log('Loading main page...');
    await page.goto('http://192.168.32.72:6133/', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    
    console.log('URL:', page.url());
    
    // Check page content
    const bodyText = await page.evaluate(() => document.body.innerHTML.slice(0, 500));
    console.log('Body preview:', bodyText.replace(/\n/g, ' ').slice(0, 200));
    
    // Look for project selector
    const selects = await page.$$('select');
    console.log('Select elements:', selects.length);
    
    // Try navigating directly to project
    console.log('\nNavigating to test-small project...');
    await page.goto('http://192.168.32.72:6133/test-small', { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(3000);
    
    console.log('URL after project nav:', page.url());
    
    // Check if canvas is loaded
    const cyCanvas = await page.$('#cy, canvas');
    console.log('Canvas found:', !!cyCanvas);
    
    // Check chat elements
    const chatPanel = await page.$('#chatPanel, #chatPanelWrapper');
    console.log('Chat panel found:', !!chatPanel);
    
    // Try to click chat toggle
    const chatToggle = await page.$('#chatToggle');
    console.log('Chat toggle:', !!chatToggle);
    if (chatToggle) {
      await chatToggle.click();
      await page.waitForTimeout(1000);
      
      // Check if chat is open
      const isOpen = await page.evaluate(() => {
        const panel = document.getElementById('chatPanel');
        return panel ? (panel.classList.contains('open') || panel.style.left === '0px') : false;
      });
      console.log('Chat panel open:', isOpen);
      
      // Find input
      const inputs = await page.$$('input[type="text"], textarea');
      console.log('Text inputs:', inputs.length);
      
      // Try typing
      const chatInput = await page.$('#chatInput');
      if (chatInput) {
        await chatInput.fill('hello');
        await page.waitForTimeout(500);
        
        // Find button
        const btns = await page.$$('button');
        console.log('Buttons found:', btns.length);
        
        for (const btn of btns.slice(0, 5)) {
          const txt = await btn.innerText();
          console.log('  Button:', txt.trim().slice(0, 30));
        }
      }
    }
    
    // Check current session info
    const sessionInfo = await page.evaluate(() => {
      return { 
        projectId: window.currentProjectId,
        sessionId: window.currentSessionId,
        chatSending: window.chatSending
      };
    });
    console.log('Session info:', sessionInfo);
    
  } finally {
    await browser.close();
  }
}

test().catch(e => console.error('Fatal:', e.message));
