#!/usr/bin/env node
/**
 * NetOps 深度测试 v2 - 基于 API 的测试
 * 通过直接调用 chat API 测试 AI 能力，操作解析和验证在测试层完成
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const SERVER = '192.168.32.72';
const PORT = 6133;
const BASE = `http://${SERVER}:${PORT}`;
const REPORT_DIR = '/root/netops/test-reports/comprehensive';

// ===== 工具函数 =====
function post(p, data, timeout = 60000) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    const url = require('url').parse(BASE + p);
    url.method = 'POST';
    url.headers = { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) };
    const req = http.request(url, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch(e) { resolve(d); } });
    });
    req.setTimeout(timeout, () => { req.destroy(); reject(new Error('timeout')); });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function get(p) {
  return new Promise((resolve, reject) => {
    http.get(BASE + p, res => {
      let d = '';
      res.on('data', c => d += c);
      res.on('end', () => { try { resolve(JSON.parse(d)); } catch(e) { resolve(d); } });
    }).on('error', reject);
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function log(msg) {
  const ts = new Date().toISOString().slice(11, 19);
  console.log(`[${ts}] ${msg}`);
  fs.appendFileSync(path.join(REPORT_DIR, 'run.log'), `[${ts}] ${msg}\n`);
}

// ===== 聊天 API =====
async function sendChat(projId, sessionId, text, withTopo = false, topo = null) {
  const payload = { projectId: projId, sessionId, text, withTopo };
  if (topo) payload.topology = topo;
  return post('/api/chat/send', payload, 120000);
}

// ===== 操作解析（从回复文本中提取）=====
function parseOpsFromReply(text) {
  const ops = [];
  const lines = text.split('\n');
  for (const line of lines) {
    const m = line.match(/\[op\]\s*(.+)/i);
    if (!m) continue;
    const opStr = m[1].trim();
    
    // add:id=xxx,type=xxx,x=xxx,y=xxx
    const addM = opStr.match(/^add\s*:\s*(.+)/i);
    if (addM) {
      const params = {};
      addM[1].split(/[,，]/).forEach(pair => {
        const [k, v] = pair.split('=').map(s => s.trim());
        if (k && v) params[k] = v;
      });
      ops.push({ action: 'add', ...params });
      continue;
    }
    
    // add_edge:from=xxx,to=xxx,src_port=xxx,tgt_port=xxx
    const edgeM = opStr.match(/add_edge\s*:\s*(.+)/i);
    if (edgeM) {
      const params = {};
      edgeM[1].split(/[,，]/).forEach(pair => {
        const [k, v] = pair.split('=').map(s => s.trim());
        if (k && v) params[k] = v;
      });
      ops.push({ action: 'add_edge', ...params });
      continue;
    }
    
    // del:id=xxx
    const delM = opStr.match(/^del\s*:\s*(.+)/i);
    if (delM) {
      const params = {};
      delM[1].split(/[,，]/).forEach(pair => {
        const [k, v] = pair.split('=').map(s => s.trim());
        if (k && v) params[k] = v;
      });
      ops.push({ action: 'delete', ...params });
      continue;
    }
    
    // del_edge:from=xxx,to=xxx
    const delEdgeM = opStr.match(/del_edge\s*:\s*(.+)/i);
    if (delEdgeM) {
      const params = {};
      delEdgeM[1].split(/[,，]/).forEach(pair => {
        const [k, v] = pair.split('=').map(s => s.trim());
        if (k && v) params[k] = v;
      });
      ops.push({ action: 'delete_edge', ...params });
      continue;
    }
  }
  return ops;
}

function validateOps(ops) {
  // 验证操作格式
  const issues = [];
  const addIds = new Set();
  const validTypes = ['router', 'switch', 'firewall', 'server', 'pc', 'cloud', 'wan', 'router_core', 'switch_core', 'switch_access'];
  
  for (const op of ops) {
    if (op.action === 'add') {
      if (!op.id) issues.push('add操作缺少id');
      if (op.type && !validTypes.includes(op.type.toLowerCase())) issues.push(`无效设备类型: ${op.type}`);
      if (op.id) addIds.add(op.id);
    }
    if (op.action === 'add_edge') {
      if (!op.from && !op.source) issues.push('add_edge缺少from/source');
      if (!op.to && !op.target) issues.push('add_edge缺少to/target');
      const src = op.from || op.source;
      const tgt = op.to || op.target;
      if (src && !addIds.has(src)) issues.push(`引用了不存在的设备: ${src}`);
      if (tgt && !addIds.has(tgt)) issues.push(`引用了不存在的设备: ${tgt}`);
    }
    if (op.action === 'delete') {
      if (!op.id) issues.push('delete操作缺少id');
    }
  }
  return issues;
}

// ===== 评分函数 =====
function scoreHumanization(text) {
  if (!text || text.length === 0) return 1;
  let score = 3;
  
  // 加分项
  if (text.includes('建议') || text.includes('推荐') || text.includes('可以') || text.includes('推荐')) score += 0.5;
  if (text.includes('其实') || text.includes('不过') || text.includes('但') || text.includes('不过我')) score += 0.3;
  if (text.includes('这个') && text.includes('可能')) score += 0.3;
  if (text.includes('没问题') || text.includes('这挺') || text.includes('挺不错')) score += 0.3;
  if (text.length > 200) score += 0.3;
  if (text.includes('好的') && text.includes('我')) score += 0.3;
  if (text.includes('嗯') || text.includes('我理解') || text.includes('明白了')) score += 0.3;
  if (text.includes('！') && text.includes('。')) score += 0.2;
  if (text.includes('首先') && text.includes('然后') && text.includes('最后')) score += 0.3;
  if (text.includes('有点') || text.includes('应该') || text.includes('可能需要')) score += 0.2;
  if (text.includes('可以看看') || text.includes('建议检查') || text.includes('建议考虑')) score += 0.3;
  
  // 扣分项
  if (text.includes('【格式】') && text.includes('[op]')) score -= 0.5;
  if (text.length < 20) score -= 1;
  if (text.includes('请稍等') || text.includes('正在处理')) score -= 0.5;
  if (text.includes('指令格式') || text.includes('以下为')) score -= 0.3;
  if (text.includes('好的') && text.length < 30) score -= 0.5;
  if (text.includes('好的，') && text.length < 50) score -= 0.3;
  if (text.includes('好的，我') && text.length < 80) score -= 0.2;
  if (text.includes('好的，我将') || text.includes('好的，请')) score -= 0.3;
  
  return Math.max(1, Math.min(5, Math.round(score * 10) / 10));
}

// ===== 测试场景 =====
const humanizeScenarios = [
  { id: 'small-office', text: '帮我规划一个小办公室网络，3台PC，1台服务器', expect_ops: true, desc: '小办公室规划' },
  { id: 'topology-issue', text: '这个网络有什么问题？', expect_ops: false, desc: '拓扑问题分析' },
  { id: 'expand-wifi', text: '我想扩展网络，要加无线AP，怎么做？', expect_ops: false, desc: '网络扩展建议' },
  { id: 'security-check', text: '帮我检查一下这个拓扑有没有安全隐患', expect_ops: false, desc: '安全检查' },
  { id: 'router-vs-switch', text: '路由器和交换机的区别是什么？', expect_ops: false, desc: '技术知识问答' },
  { id: '10g-assessment', text: '这个网络能跑万兆吗？', expect_ops: false, desc: '性能评估' },
  { id: 'datacenter', text: '帮我生成一个数据中心的拓扑，10台服务器，2台核心交换机', expect_ops: true, desc: '数据中心生成' },
];

const topoScenarios = [
  { id: 'small-topology', desc: '小规模拓扑 (3-5节点)', text: '添加一台核心路由器，再加一台接入交换机，PC接交换机', scale: 'small', projId: 'test-small' },
  { id: 'medium-topology', desc: '中等规模拓扑 (10-20节点)', text: '帮我在当前拓扑添加8台PC，分两组，每组4台，每组接一台接入交换机', scale: 'medium', projId: 'test-medium' },
  { id: 'large-topology', desc: '大规模拓扑 (50节点)', text: '生成一个50台设备的企业网络拓扑，包含2台核心路由器，4台汇聚交换机，8台接入交换机，其余为PC和服务器', scale: 'large', projId: 'test-large' },
];

// ===== 主测试函数 =====
async function runHumanizeTest(scenario) {
  const projId = 'test-humanize';
  const sessionId = `hz-${scenario.id}-${Date.now()}`;
  log(`[人性化] ${scenario.id} - ${scenario.desc}`);
  
  try {
    const res = await sendChat(projId, sessionId, scenario.text, false);
    const reply = res.reply || '（无回复）';
    const apiOps = res.operations || [];
    const textOps = parseOpsFromReply(reply);
    const allOps = apiOps.length > 0 ? apiOps : textOps;
    const score = scoreHumanization(reply);
    
    const record = {
      timestamp: new Date().toISOString(),
      scenario: scenario.id,
      desc: scenario.desc,
      score,
      reply_length: reply.length,
      ops_from_api: apiOps.length,
      ops_from_text: textOps.length,
      reply_preview: reply.slice(0, 200).replace(/\n/g, ' '),
    };
    
    log(`  评分: ${score}/5 | API操作: ${apiOps.length} | 文本操作: ${textOps.length} | 长度: ${reply.length}`);
    
    if (scenario.expect_ops && allOps.length > 0) {
      const issues = validateOps(allOps);
      record.op_validation = issues.length === 0 ? 'PASS' : `ISSUES: ${issues.join('; ')}`;
      record.op_validation_issues = issues;
      log(`  操作验证: ${record.op_validation}`);
      
      // 追问测试
      await sleep(2000);
      const followup = await sendChat(projId, sessionId, '这个设计有什么可以改进的地方？', false);
      const fscore = scoreHumanization(followup.reply || '');
      record.followup_score = fscore;
      record.followup_preview = (followup.reply || '').slice(0, 150).replace(/\n/g, ' ');
      log(`  追问评分: ${fscore}/5`);
    }
    
    return record;
  } catch(e) {
    log(`  错误: ${e.message}`);
    return { scenario: scenario.id, error: e.message, timestamp: new Date().toISOString() };
  }
}

async function runTopoTest(scenario) {
  const { id, desc, text, projId } = scenario;
  const sessionId = `topo-${id}-${Date.now()}`;
  log(`[拓扑] ${id} - ${desc}`);
  
  try {
    const res = await sendChat(projId, sessionId, text, false);
    const reply = res.reply || '（无回复）';
    const apiOps = res.operations || [];
    const textOps = parseOpsFromReply(reply);
    const allOps = apiOps.length > 0 ? apiOps : textOps;
    const score = scoreHumanization(reply);
    
    const record = {
      timestamp: new Date().toISOString(),
      scenario: id,
      desc,
      text,
      humanize_score: score,
      ops_count: allOps.length,
      ops_from_api: apiOps.length,
      ops_from_text: textOps.length,
      reply_length: reply.length,
      reply_preview: reply.slice(0, 200).replace(/\n/g, ' '),
    };
    
    log(`  人性化评分: ${score}/5 | 操作数: ${allOps.length}`);
    
    if (allOps.length > 0) {
      const issues = validateOps(allOps);
      record.op_validation = issues.length === 0 ? 'PASS' : `ISSUES: ${issues.join('; ')}`;
      record.op_validation_issues = issues;
      log(`  操作验证: ${record.op_validation}`);
      
      // 统计节点类型分布
      const addOps = allOps.filter(o => o.action === 'add' || o.action === 'add_node' || o.action === 'add_device');
      const edgeOps = allOps.filter(o => o.action === 'add_edge' || o.action === 'connect');
      record.devices_requested = addOps.length;
      record.connections_requested = edgeOps.length;
      
      const typeCount = {};
      addOps.forEach(o => { const t = (o.type || 'unknown').toLowerCase(); typeCount[t] = (typeCount[t] || 0) + 1; });
      record.device_types = typeCount;
      
      log(`  设备: ${JSON.stringify(typeCount)}, 连线: ${edgeOps.length}`);
    }
    
    return record;
  } catch(e) {
    log(`  错误: ${e.message}`);
    return { scenario: id, error: e.message, timestamp: new Date().toISOString() };
  }
}

async function runRegionTests() {
  log('[区域] 开始区域管理测试');
  const results = [];
  const topo = await get(`/api/projects/Admin/topo`).catch(() => ({ nodes: [], edges: [] }));
  
  const tests = [
    { text: '帮我规划VLAN，IT部门、财务部门、生产部门分开', desc: 'VLAN规划' },
    { text: '添加一个无线控制器和3个AP', desc: '无线网络' },
    { text: '帮我设计一个三区域网络：信任区、半信任区、不信任区', desc: '安全区域' },
  ];
  
  for (const t of tests) {
    const sessionId = `region-${Date.now()}`;
    try {
      const res = await sendChat('Admin', sessionId, t.text, true, topo);
      const score = scoreHumanization(res.reply || '');
      const ops = parseOpsFromReply(res.reply || '');
      results.push({
        desc: t.desc,
        text: t.text,
        score,
        ops_count: ops.length,
        reply_preview: (res.reply || '').slice(0, 150).replace(/\n/g, ' ')
      });
      log(`  ${t.desc}: 评分 ${score}/5, 操作 ${ops.length}`);
    } catch(e) {
      results.push({ desc: t.desc, error: e.message });
      log(`  ${t.desc}: 错误 ${e.message}`);
    }
    await sleep(2000);
  }
  return results;
}

async function main() {
  log('========== NetOps 8小时深度测试开始 ==========');
  log(`时间: ${new Date().toISOString()}`);
  
  // 阶段1: 环境确认
  log('--- 阶段1: 环境确认 ---');
  const serverOk = await get('/').then(() => true).catch(() => false);
  log(`Server: ${serverOk ? '✅ OK' : '❌ FAIL'}`);
  
  // 阶段2: 人性化测试
  log('--- 阶段2: AI人性化测试 ---');
  const humanizeResults = [];
  for (const s of humanizeScenarios) {
    const r = await runHumanizeTest(s);
    humanizeResults.push(r);
    await sleep(2500);
  }
  
  // 阶段3: 拓扑规模测试
  log('--- 阶段3: 多规模拓扑测试 ---');
  const topoResults = [];
  for (const s of topoScenarios) {
    const r = await runTopoTest(s);
    topoResults.push(r);
    await sleep(3000);
  }
  
  // 阶段4: 区域管理测试
  log('--- 阶段4: 移动与区域管理测试 ---');
  const regionResults = await runRegionTests();
  
  // 计算统计
  const hScores = humanizeResults.filter(r => r.score).map(r => r.score);
  const avgH = hScores.length ? (hScores.reduce((a, b) => a + b, 0) / hScores.length).toFixed(2) : 'N/A';
  const tScores = topoResults.filter(r => r.humanize_score).map(r => r.humanize_score);
  const avgT = tScores.length ? (tScores.reduce((a, b) => a + b, 0) / tScores.length).toFixed(2) : 'N/A';
  
  log(`--- 测试完成 ---`);
  log(`平均人性化评分: ${avgH}/5`);
  log(`平均拓扑评分: ${avgT}/5`);
  
  // 保存结果
  const report = {
    generated_at: new Date().toISOString(),
    server_status: serverOk,
    humanize_tests: humanizeResults,
    topo_tests: topoResults,
    region_tests: regionResults,
    stats: { avg_humanize: avgH, avg_topo: avgT }
  };
  
  fs.writeFileSync(path.join(REPORT_DIR, 'test_results.json'), JSON.stringify(report, null, 2));
  
  // 生成 Markdown 报告
  let md = `# NetOps 深度测试报告\n\n`;
  md += `> 生成时间: ${report.generated_at}\n\n`;
  md += `## 概览\n\n`;
  md += `| 指标 | 数值 |\n|------|------|\n`;
  md += `| 平均人性化评分 | **${avgH}/5** |\n`;
  md += `| 平均拓扑评分 | **${avgT}/5** |\n`;
  md += `| Server状态 | ${serverOk ? '✅ 正常' : '❌ 异常'} |\n\n`;
  
  md += `## 人性化测试详情\n\n`;
  md += `| 场景 | 评分 | 文字长度 | API操作 | 文本操作 |\n`;
  md += `|------|------|---------|---------|---------|\n`;
  for (const r of humanizeResults) {
    md += `| ${r.scenario} | ${r.score || 'ERR'}/5 | ${r.reply_length || '?'} | ${r.ops_from_api || 0} | ${r.ops_from_text || 0} |\n`;
  }
  md += `\n`;
  
  md += `## 拓扑测试详情\n\n`;
  md += `| 场景 | 规模 | 人性化 | 操作数 | 操作验证 |\n`;
  md += `|------|------|--------|--------|---------|\n`;
  for (const r of topoResults) {
    md += `| ${r.scenario} | ${r.desc} | ${r.humanize_score || '?'}/5 | ${r.ops_count || 0} | ${r.op_validation || 'N/A'} |\n`;
  }
  
  md += `\n## 区域管理测试\n\n`;
  md += `| 场景 | 评分 | 操作数 |\n`;
  md += `|------|------|--------|\n`;
  for (const r of regionResults) {
    md += `| ${r.desc} | ${r.score || '?'}/5 | ${r.ops_count || 0} |\n`;
  }
  
  md += `\n## AI回复质量分析\n\n`;
  const good = humanizeResults.filter(r => (r.score || 0) >= 4).length;
  const mid = humanizeResults.filter(r => (r.score || 0) === 3).length;
  const bad = humanizeResults.filter(r => (r.score || 0) < 3).length;
  md += `- 🟢 优秀 (4-5分): ${good} 个场景\n`;
  md += `- 🟡 一般 (3分): ${mid} 个场景\n`;
  md += `- 🔴 较差 (1-2分): ${bad} 个场景\n\n`;
  
  md += `## 发现与建议\n\n`;
  // 收集问题
  const issues = [];
  humanizeResults.filter(r => r.score && r.score < 3.5).forEach(r => {
    issues.push(`**${r.scenario}** 评分偏低(${r.score}/5): ${r.reply_preview}`);
  });
  topoResults.filter(r => r.op_validation && !r.op_validation.startsWith('PASS')).forEach(r => {
    issues.push(`**${r.scenario}** 操作验证失败: ${r.op_validation}`);
  });
  
  if (issues.length > 0) {
    issues.forEach(i => { md += `- ${i}\n`; });
  } else {
    md += `- 暂无明显问题\n`;
  }
  
  fs.writeFileSync(path.join(REPORT_DIR, 'report.md'), md);
  log('报告已保存: test_results.json, report.md');
  
  // 更新 findings.md
  const findings = `\n\n## 测试运行 ${new Date().toISOString()}\n\n`;
  const summary = `- 人性化评分: ${avgH}/5 (${humanizeScenarios.length}个场景)\n`;
  const summary2 = `- 拓扑评分: ${avgT}/5 (${topoScenarios.length}个规模测试)\n`;
  const summary3 = `- 区域测试: ${regionResults.length}个场景\n`;
  fs.appendFileSync(path.join(REPORT_DIR, 'findings.md'), findings + summary + summary2 + summary3);
  
  return report;
}

main().catch(e => { log(`FATAL: ${e.message}`); process.exit(1); });
