const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const BASE_URL = 'http://192.168.32.72:6133';
const OUT_DIR = '/root/netops/stress_tests';
const TOTAL_SECONDS = 28800;
const CYCLE_SECONDS = 300;
const TOTAL_CYCLES = Math.floor(TOTAL_SECONDS / CYCLE_SECONDS);

let startTime = Date.now();
let cycleResults = [];
let bugs = [];

if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR, { recursive: true });

function ts() {
  return new Date().toISOString().replace('T', ' ').substring(0, 19);
}
function log(msg) {
  const elapsed = Math.floor((Date.now() - startTime) / 1000);
  console.log(`[${ts()}] [${elapsed}s] ${msg}`);
}
async function wait(ms) { return new Promise(r => setTimeout(r, ms)); }

function screenshot(page, name) {
  if (!page) return null;
  const t = new Date();
  const nameStr = `${name}_${t.getHours().toString().padStart(2,'0')}${t.getMinutes().toString().padStart(2,'0')}${t.getSeconds().toString().padStart(2,'0')}.png`;
  const p = path.join(OUT_DIR, nameStr);
  try { page.screenshot({ path: p, fullPage: false }).catch(() => {}); } catch {}
  return p;
}

function getTopologyInfo(page) {
  try {
    if (!page || page.isClosed()) return { nodes: 0, edges: 0 };
    return page.evaluate(() => {
      if (!window.cy) return { nodes: 0, edges: 0 };
      return { nodes: window.cy.nodes().length, edges: window.cy.edges().length };
    });
  } catch { return { nodes: 0, edges: 0 }; }
}

function getBodyText(page) {
  try {
    if (!page || page.isClosed()) return '';
    return page.evaluate(() => document.body.innerText || '');
  } catch { return ''; }
}

// ─── Project Management ──────────────────────────────────────────────────────

async function createProject(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  
  await page.goto(BASE_URL, { timeout: 15000 });
  await wait(2000);
  
  // Click 新建项目
  await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
      if (btn.textContent.includes('新建项目') || btn.textContent.includes('＋')) {
        btn.click(); return;
      }
    }
  });
  await wait(2000);
  
  // Fill name
  await page.evaluate((n) => {
    const inputs = document.querySelectorAll('input');
    for (const inp of inputs) {
      if (inp.placeholder.includes('项目名称') && inp.offsetParent !== null) {
        inp.value = n;
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        return;
      }
    }
  }, name);
  await wait(500);
  
  // Click 创建
  await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    for (const btn of btns) {
      if (btn.textContent.trim() === '创建' && btn.offsetParent !== null) {
        btn.click(); return;
      }
    }
  });
  await wait(4000);
  
  return { context, page };
}

async function enterProject(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  
  await page.goto(BASE_URL, { timeout: 15000 });
  await wait(2000);
  
  const found = await page.evaluate((n) => {
    const rows = document.querySelectorAll('tr');
    for (const row of rows) {
      if (row.textContent.includes(n)) {
        const btns = row.querySelectorAll('button');
        for (const btn of btns) {
          if (btn.textContent.includes('进入')) { btn.click(); return true; }
        }
      }
    }
    return false;
  }, name);
  
  if (!found) {
    await page.goto(`${BASE_URL}/${encodeURIComponent(name)}`, { timeout: 15000 });
    await wait(3000);
  } else {
    await wait(3000);
  }
  
  return { context, page };
}

async function deleteProject(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  try {
    await page.goto(BASE_URL, { timeout: 15000 });
    await wait(2000);
    await page.evaluate((n) => {
      const rows = document.querySelectorAll('tr');
      for (const row of rows) {
        if (row.textContent.includes(n)) {
          const btns = row.querySelectorAll('button');
          for (const btn of btns) {
            if (btn.textContent.includes('删除')) { btn.click(); return; }
          }
        }
      }
    }, name);
    await wait(1000);
    await page.evaluate(() => {
      const btns = document.querySelectorAll('button');
      for (const btn of btns) {
        if (btn.textContent.trim() === '确认' || btn.textContent.trim() === '确定') { btn.click(); return; }
      }
    });
    await wait(1000);
  } catch {} finally {
    await context.close().catch(() => {});
  }
}

// ─── AI Chat ─────────────────────────────────────────────────────────────────

async function sendMessage(page, msg, waitSec = 6) {
  try {
    if (!page || page.isClosed()) return false;
    
    // Use Playwright's native fill on the AI textarea
    const selector = 'textarea[placeholder*="问题"]';
    await page.locator(selector).scrollIntoViewIfNeeded().catch(() => {});
    await page.locator(selector).fill(msg).catch(() => {});
    await wait(500);
    await page.keyboard.press('Enter');
    await wait(waitSec * 1000);
    return true;
  } catch { return false; }
}

async function clickExecute(page) {
  try {
    return await page.evaluate(() => {
      const btns = document.querySelectorAll('button');
      for (const btn of btns) {
        if (btn.textContent.includes('执行') && btn.textContent.includes('操作')) {
          btn.scrollIntoView();
          btn.click();
          return true;
        }
      }
      return false;
    });
  } catch { return false; }
}

// ─── Bug Recording ───────────────────────────────────────────────────────────

function recordBug(severity, title, description, sp) {
  bugs.push({ timestamp: ts(), severity, title, description: description.substring(0, 200), screenshot: sp });
  log(`  [BUG][${severity}] ${title}`);
}

// ─── Hourly Report ───────────────────────────────────────────────────────────

function saveHourlyReport(hour) {
  const recent = cycleResults.slice(-50);
  const tp = recent.reduce((s, r) => s + (r.passed?.length || 0), 0);
  const tf = recent.reduce((s, r) => s + (r.failed?.length || 0), 0);
  const report = `
═══════════════════════════════════════════
  NetOps 8小时测试 - 第${hour}小时阶段报告  ${ts()}
═══════════════════════════════════════════
通过: ${tp}  失败: ${tf}
严重Bug: ${bugs.filter(b=>b.severity==='CRITICAL'||b.severity==='HIGH').length}
中Bug: ${bugs.filter(b=>b.severity==='MEDIUM').length}
低Bug: ${bugs.filter(b=>b.severity==='LOW').length}
最近Bug:
${bugs.slice(-5).map(b=>`  [${b.severity}] ${b.title}: ${b.description.substring(0,80)}`).join('\n')||'  无'}
═══════════════════════════════════════════
`;
  fs.writeFileSync(path.join(OUT_DIR, `hourly_h${hour}.txt`), report);
  log(`Hourly report #${hour} saved`);
}

// ─── Test Scenarios ─────────────────────────────────────────────────────────

async function runCycleA(browser, cycleNum) {
  const name = `压测A-${Date.now()}`;
  const result = { cycle: `A-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `A${cycleNum}_01_proj`);
    
    await sendMessage(page, '添加3台路由器和2台交换机，连成星型拓扑', 8);
    screenshot(page, `A${cycleNum}_02_added`);
    await clickExecute(page);
    await wait(5000);
    
    const i1 = await getTopologyInfo(page);
    if (i1.nodes >= 5) result.passed.push(`星型拓扑-设备(${i1.nodes})`);
    else result.failed.push(`星型拓扑-设备不足(${i1.nodes}/5)`);
    
    await sendMessage(page, '把所有路由器连接起来，形成全互联拓扑', 8);
    screenshot(page, `A${cycleNum}_03_mesh`);
    await clickExecute(page);
    await wait(5000);
    
    const i2 = await getTopologyInfo(page);
    if (i2.edges >= 3) result.passed.push(`全互联-连线(${i2.edges})`);
    else result.failed.push(`全互联-连线不足(${i2.edges}/3)`);
    
    await sendMessage(page, '为所有设备分配192.168.x.x网段IP', 8);
    screenshot(page, `A${cycleNum}_04_ip`);
    await clickExecute(page);
    await wait(5000);
    screenshot(page, `A${cycleNum}_05_final`);
    result.passed.push('IP分配命令执行');
    
    log(`  A-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `A-${cycleNum} 崩溃`, e.message, screenshot(page, `A${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleB(browser, cycleNum) {
  const name = `压测B-${Date.now()}`;
  const result = { cycle: `B-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `B${cycleNum}_01_proj`);
    
    await sendMessage(page, '添加一台路由器ID为R1', 6);
    await clickExecute(page);
    await wait(4000);
    screenshot(page, `B${cycleNum}_02_first`);
    
    await sendMessage(page, '再添加一台路由器ID也为R1', 6);
    screenshot(page, `B${cycleNum}_03_dup`);
    const b1 = await getBodyText(page);
    if (b1.includes('冲突') || b1.includes('重复') || b1.includes('已存在') || b1.includes('错误') || b1.includes('失败')) {
      result.passed.push('同名设备-校验');
    } else result.failed.push('同名设备-未检测');
    
    await clickExecute(page);
    await wait(4000);
    screenshot(page, `B${cycleNum}_04_exec`);
    
    await sendMessage(page, '添加R2和R3，然后连接R2的GE0/0/0到R3，再连接R2的GE0/0/0到R1', 8);
    screenshot(page, `B${cycleNum}_05_port`);
    const b2 = await getBodyText(page);
    if (b2.includes('端口') || b2.includes('占用') || b2.includes('已用') || b2.includes('冲突')) {
      result.passed.push('端口冲突-校验');
    } else result.failed.push('端口冲突-未检测');
    
    log(`  B-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `B-${cycleNum} 崩溃`, e.message, screenshot(page, `B${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleC(browser, cycleNum) {
  const name = `压测C-${Date.now()}`;
  const result = { cycle: `C-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `C${cycleNum}_01_proj`);
    
    await sendMessage(page, '添加R1和R2两台路由器', 6);
    await clickExecute(page);
    await wait(4000);
    screenshot(page, `C${cycleNum}_02_added`);
    const i0 = await getTopologyInfo(page);
    
    await sendMessage(page, '删除R1，然后删除R999（不存在），再添加R3', 8);
    screenshot(page, `C${cycleNum}_03_tx`);
    const b = await getBodyText(page);
    if (b.includes('回滚') || b.includes('事务') || b.includes('失败') || b.includes('不存在')) {
      result.passed.push('回滚-提示');
    } else result.failed.push('回滚-无提示');
    
    await clickExecute(page);
    await wait(6000);
    screenshot(page, `C${cycleNum}_04_exec`);
    const i1 = await getTopologyInfo(page);
    if (i1.nodes <= i0.nodes + 1) {
      result.passed.push(`回滚-节点正确(${i0.nodes}->${i1.nodes})`);
    } else result.failed.push(`回滚-节点异常(${i0.nodes}->${i1.nodes})`);
    
    log(`  C-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `C-${cycleNum} 崩溃`, e.message, screenshot(page, `C${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleD(browser, cycleNum) {
  const name = `压测D-${Date.now()}`;
  const result = { cycle: `D-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `D${cycleNum}_01_proj`);
    
    await sendMessage(page, '把R1的GE0/0/0连接到R3', 6);
    screenshot(page, `D${cycleNum}_02_nonexist`);
    const b1 = await getBodyText(page);
    if (b1.includes('不存在') || b1.includes('未找到') || b1.includes('错误') || b1.includes('失败')) {
      result.passed.push('不存在设备-AI拒绝');
    } else result.failed.push('不存在设备-AI未拒绝');
    
    await sendMessage(page, '添加R1、R2、R3三台路由器', 6);
    await clickExecute(page);
    await wait(4000);
    screenshot(page, `D${cycleNum}_03_added`);
    
    await sendMessage(page, '把R1的GE0/0/0连接到R2，再把R1的GE0/0/0连接到R3', 8);
    screenshot(page, `D${cycleNum}_04_dup`);
    const b2 = await getBodyText(page);
    if (b2.includes('替代') || b2.includes('其他') || b2.includes('可用') || b2.includes('建议') || b2.includes('端口')) {
      result.passed.push('重复端口-替代方案');
    } else result.failed.push('重复端口-无替代');
    
    log(`  D-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `D-${cycleNum} 崩溃`, e.message, screenshot(page, `D${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleE(browser, cycleNum) {
  const name = `压测E-${Date.now()}`;
  const result = { cycle: `E-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `E${cycleNum}_01_proj`);
    
    await sendMessage(page, '创建20台路由器，编号R1-R20，均匀分布在500x500的画布上', 12);
    screenshot(page, `E${cycleNum}_02_creating`);
    await clickExecute(page);
    await wait(8000);
    screenshot(page, `E${cycleNum}_03_created`);
    
    const i1 = await getTopologyInfo(page);
    if (i1.nodes >= 20) result.passed.push(`大规模-20台设备(${i1.nodes})`);
    else result.failed.push(`大规模-设备不足(${i1.nodes}/20)`);
    
    await sendMessage(page, '为每台路由器连接到R1作为中心节点', 12);
    screenshot(page, `E${cycleNum}_04_connecting`);
    await clickExecute(page);
    await wait(8000);
    screenshot(page, `E${cycleNum}_05_connected`);
    
    const i2 = await getTopologyInfo(page);
    if (i2.edges >= 19) result.passed.push(`大规模-19条连线(${i2.edges})`);
    else result.failed.push(`大规模-连线不足(${i2.edges}/19)`);
    
    log(`  E-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `E-${cycleNum} 崩溃`, e.message, screenshot(page, `E${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleF(browser, cycleNum) {
  const nameA = `压测FA-${Date.now()}`;
  const nameB = `压测FB-${Date.now()}`;
  const result = { cycle: `F-${cycleNum}`, projects: [nameA, nameB], passed: [], failed: [], bugs: [] };
  let c1 = null, p1 = null, c2 = null, p2 = null;
  try {
    ({ context: c1, page: p1 } = await createProject(browser, nameA));
    screenshot(p1, `F${cycleNum}_01_projA`);
    await sendMessage(p1, '添加三台路由器R1、R2、R3', 6);
    await clickExecute(p1);
    await wait(4000);
    const iA = await getTopologyInfo(p1);
    screenshot(p1, `F${cycleNum}_02_inA`);
    
    ({ context: c2, page: p2 } = await createProject(browser, nameB));
    screenshot(p2, `F${cycleNum}_03_projB`);
    const iB = await getTopologyInfo(p2);
    if (iB.nodes === 0) result.passed.push('会话-项目B为空');
    else result.failed.push(`会话-项目B非空(${iB.nodes})`);
    
    const p1a = await enterProject(browser, nameA);
    const p1again = p1a.page;
    await wait(3000);
    screenshot(p1again, `F${cycleNum}_04_backA`);
    const iA2 = await getTopologyInfo(p1again);
    if (iA2.nodes === iA.nodes) result.passed.push('会话-项目A数据保持');
    else result.failed.push(`会话-项目A丢失(${iA.nodes}->${iA2.nodes})`);
    
    await p1again.close().catch(() => {});
    await p1a.context.close().catch(() => {});
    log(`  F-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `F-${cycleNum} 崩溃`, e.message, screenshot(p1 || p2, `F${cycleNum}_crash`));
  } finally {
    [p1, p2].forEach(p => p && p.close().catch(() => {}));
    [c1, c2].forEach(c => c && c.close().catch(() => {}));
  }
  return result;
}

async function runCycleG(browser, cycleNum) {
  const name = `压测G-${Date.now()}`;
  const result = { cycle: `G-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `G${cycleNum}_01_proj`);
    
    await page.evaluate(() => {
      const btns = document.querySelectorAll('button');
      for (const btn of btns) {
        if (btn.textContent.includes('AI 配置') || btn.textContent.includes('设置')) {
          btn.click(); return;
        }
      }
    });
    await wait(2000);
    screenshot(page, `G${cycleNum}_02_settings`);
    
    const switched = await page.evaluate(() => {
      const selects = document.querySelectorAll('select');
      for (const sel of selects) {
        if (sel.id.includes('provider') || sel.name.includes('provider')) {
          const opts = sel.options;
          if (opts.length > 1) { sel.selectedIndex = 1; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; }
        }
      }
      return false;
    });
    if (switched) {
      result.passed.push('AI配置-Provider切换');
      screenshot(page, `G${cycleNum}_03_provider`);
    } else result.failed.push('AI配置-未找到Provider');
    
    await page.evaluate(() => {
      const btns = document.querySelectorAll('button');
      for (const btn of btns) {
        if (btn.textContent.includes('关闭') || btn.textContent.includes('保存') || btn.textContent.includes('确定')) {
          btn.click(); return;
        }
      }
    });
    await wait(1000);
    
    await sendMessage(page, '你好，请确认你还在工作', 8);
    screenshot(page, `G${cycleNum}_04_response`);
    const b = await getBodyText(page);
    if (b.length > 50) result.passed.push('AI对话-正常响应');
    else result.failed.push('AI对话-响应为空');
    
    log(`  G-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('MEDIUM', `G-${cycleNum} 崩溃`, e.message, screenshot(page, `G${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleH(browser, cycleNum) {
  const name = `压测H-${Date.now()}`;
  const result = { cycle: `H-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `H${cycleNum}_01_proj`);
    
    const added = await page.evaluate(() => {
      if (!window.cy) return false;
      try {
        window.cy.add([
          { group: 'nodes', data: { id: 'MR1', label: 'MR1', type: 'router' }, position: { x: 200, y: 200 } },
          { group: 'nodes', data: { id: 'MR2', label: 'MR2', type: 'router' }, position: { x: 400, y: 200 } },
          { group: 'nodes', data: { id: 'MS1', label: 'MS1', type: 'switch' }, position: { x: 300, y: 400 } },
        ]);
        return true;
      } catch { return false; }
    });
    
    if (added) {
      result.passed.push('手动添加-JS模拟');
      screenshot(page, `H${cycleNum}_02_manual`);
      await page.evaluate(() => {
        if (!window.cy) return;
        try {
          window.cy.add([
            { group: 'edges', data: { id: 'e1', source: 'MR1', target: 'MR2', srcPort: 'GE0/0/0', tgtPort: 'GE0/0/0' } },
            { group: 'edges', data: { id: 'e2', source: 'MR1', target: 'MS1', srcPort: 'GE0/0/1', tgtPort: 'GE0/0/0' } },
          ]);
        } catch {}
      });
      await wait(2000);
      screenshot(page, `H${cycleNum}_03_edge`);
    } else result.failed.push('手动添加-cy不可用');
    
    await sendMessage(page, '当前拓扑有哪些设备？请列出ID和连线', 8);
    screenshot(page, `H${cycleNum}_04_query`);
    const b = await getBodyText(page);
    if (b.includes('MR1') && b.includes('MR2')) {
      result.passed.push('AI识别-手动设备');
    } else result.failed.push('AI识别-未识别手动');
    
    log(`  H-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('MEDIUM', `H-${cycleNum} 崩溃`, e.message, screenshot(page, `H${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleI(browser, cycleNum) {
  const name = `压测I-${Date.now()}`;
  const result = { cycle: `I-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let ctx = null, page = null;
  try {
    ({ context: ctx, page } = await createProject(browser, name));
    screenshot(page, `I${cycleNum}_01_proj`);
    
    await sendMessage(page, '添加一台路由器ID为R@#1', 6);
    screenshot(page, `I${cycleNum}_02_special`);
    const b1 = await getBodyText(page);
    if (!b1.includes('500') && !b1.includes('Internal Error')) {
      result.passed.push('异常-特殊字符-未崩溃');
    } else {
      result.failed.push('异常-特殊字符-服务器错误');
      recordBug('MEDIUM', '特殊字符错误', b1.substring(0, 100), screenshot(page, `I${cycleNum}_crash1`));
    }
    
    const longText = '添加路由器：' + '测试'.repeat(500);
    await sendMessage(page, longText, 6);
    screenshot(page, `I${cycleNum}_03_long`);
    const b2 = await getBodyText(page);
    if (!b2.includes('500') && !b2.includes('Internal Error')) {
      result.passed.push('异常-超长文本-未崩溃');
    } else {
      result.failed.push('异常-超长文本-服务器错误');
      recordBug('MEDIUM', '超长文本错误', b2.substring(0, 100), screenshot(page, `I${cycleNum}_crash2`));
    }
    
    await page.evaluate(() => {
      try {
        if (window.cy) {
          window.cy.add([{ group: 'nodes', data: { id: 'NR1', label: 'NR1', type: 'router' }, position: { x: -100, y: -200 } }]);
        }
      } catch {}
    });
    await wait(2000);
    screenshot(page, `I${cycleNum}_04_neg`);
    const b3 = await getBodyText(page);
    if (!b3.includes('500')) result.passed.push('异常-负数坐标-未崩溃');
    else result.failed.push('异常-负数坐标-服务器错误');
    
    log(`  I-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('MEDIUM', `I-${cycleNum} 崩溃`, e.message, screenshot(page, `I${cycleNum}_crash`));
  } finally {
    if (page) await page.close().catch(() => {});
    if (ctx) await ctx.close().catch(() => {});
  }
  return result;
}

async function runCycleJ(browser, cycleNum) {
  const name = `压测J-${Date.now()}`;
  const result = { cycle: `J-${cycleNum}`, project: name, passed: [], failed: [], bugs: [] };
  let c1 = null, p1 = null, c2 = null, p2 = null;
  try {
    ({ context: c1, page: p1 } = await createProject(browser, name));
    screenshot(p1, `J${cycleNum}_01_projA`);
    await sendMessage(p1, '添加两台路由器R1和R2', 6);
    await clickExecute(p1);
    await wait(4000);
    screenshot(p1, `J${cycleNum}_02_A_added`);
    const iA = await getTopologyInfo(p1);
    
    ({ context: c2, page: p2 } = await createProject(browser, name));
    screenshot(p2, `J${cycleNum}_03_B_open`);
    await wait(3000);
    const iB = await getTopologyInfo(p2);
    screenshot(p2, `J${cycleNum}_04_B_sync`);
    
    if (iB.nodes >= 2 || iB.nodes >= iA.nodes * 0.5) {
      result.passed.push(`WebSocket-已同步(节点${iB.nodes})`);
    } else {
      result.failed.push(`WebSocket-未同步(A:${iA.nodes} B:${iB.nodes})`);
      recordBug('MEDIUM', `J-${cycleNum} WebSocket不同步`, `A有${iA.nodes} B有${iB.nodes}`, screenshot(p2, `J${cycleNum}_sync_fail`));
    }
    
    log(`  J-${cycleNum}: ✓${result.passed.length} ✗${result.failed.length}`);
  } catch (e) {
    result.failed.push(`崩溃: ${e.message.substring(0,80)}`);
    recordBug('HIGH', `J-${cycleNum} 崩溃`, e.message, screenshot(p1 || p2, `J${cycleNum}_crash`));
  } finally {
    [p1, p2].forEach(p => p && p.close().catch(() => {}));
    [c1, c2].forEach(c => c && c.close().catch(() => {}));
  }
  return result;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

const runners = [runCycleA, runCycleB, runCycleC, runCycleD, runCycleE,
                 runCycleF, runCycleG, runCycleH, runCycleI, runCycleJ];
const TYPES = ['A','B','C','D','E','F','G','H','I','J'];

async function main() {
  log(`╔══════════════════════════════════════════╗`);
  log(`║   NetOps 8小时全功能压力测试启动         ║`);
  log(`║   目标: ${BASE_URL.padEnd(35)}║`);
  log(`║   计划: ${TOTAL_CYCLES}循环(${CYCLE_SECONDS}s/循环)`.padEnd(50) + '║');
  log(`╚══════════════════════════════════════════╝`);
  
  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });
  
  let cycleIndex = 0;
  let hourIndex = 0;
  const endTime = Date.now() + TOTAL_SECONDS * 1000;
  
  while (Date.now() < endTime && cycleIndex < TOTAL_CYCLES) {
    const runner = runners[cycleIndex % runners.length];
    const ctype = TYPES[cycleIndex % runners.length];
    const cnum = cycleIndex + 1;
    
    log(`── 循环 ${cnum}/${TOTAL_CYCLES} (${ctype}) ──`);
    const t0 = Date.now();
    const r = await runner(browser, cnum).catch(e => ({
      cycle: `${ctype}-${cnum}`, passed: [], failed: [`致命: ${e.message.substring(0,100)}`]
    }));
    const elapsed = Date.now() - t0;
    
    cycleResults.push(r);
    
    const hrs = Math.floor((Date.now() - startTime) / 3600000);
    if (hrs >= hourIndex + 1) { hourIndex++; saveHourlyReport(hourIndex); }
    
    const rem = CYCLE_SECONDS * 1000 - elapsed;
    if (rem > 0) { log(`  等待 ${Math.round(rem/1000)}s...`); await wait(rem); }
    cycleIndex++;
  }
  
  await browser.close();
  
  const tp = cycleResults.reduce((s, r) => s + (r.passed?.length||0), 0);
  const tf = cycleResults.reduce((s, r) => s + (r.failed?.length||0), 0);
  const rate = tp + tf > 0 ? (tp/(tp+tf)*100).toFixed(1) + '%' : 'N/A';
  
  let summary = '\n' + '═'.repeat(70) + '\n';
  summary += `  NetOps 8小时全功能压力测试 - 最终报告  ${ts()}\n`;
  summary += '═'.repeat(70) + '\n';
  summary += `测试地址: ${BASE_URL}\n`;
  summary += `实际循环: ${cycleResults.length}/${TOTAL_CYCLES}\n`;
  summary += `总通过项: ${tp}  |  总失败项: ${tf}  |  通过率: ${rate}\n`;
  summary += '\nBug列表:\n';
  bugs.forEach((b, i) => {
    summary += `  [${i+1}][${b.severity}] ${b.title}\n`;
    summary += `      ${b.description}\n`;
    summary += `      ${b.timestamp}\n`;
  });
  summary += '\n各循环汇总:\n';
  cycleResults.forEach(r => summary += `  ${r.cycle}: ✓${r.passed?.length||0} ✗${r.failed?.length||0}\n`);
  summary += '═'.repeat(70) + '\n';
  
  const rp = path.join(OUT_DIR, `final_report_${Date.now()}.txt`);
  fs.writeFileSync(rp, summary);
  fs.writeFileSync(path.join(OUT_DIR, `results_${Date.now()}.json`), JSON.stringify({
    timestamp: ts(), baseUrl: BASE_URL, totalCycles: cycleResults.length,
    totalPassed: tp, totalFailed: tf, passRate: rate, bugs, cycleResults
  }, null, 2));
  
  console.log(summary);
  log(`报告: ${rp}`);
}

main().catch(e => { console.error('Fatal:', e); process.exit(1); });
