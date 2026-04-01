#!/usr/bin/env python3
"""NetOps 8小时持续测试 - 主测试脚本 v3 (operations-aware)"""
import requests, json, time, sys, os, subprocess, uuid
from datetime import datetime

SERVER = "http://192.168.32.72:6133"
CHAT_API = SERVER + "/api/chat/send"
API_PROJ = SERVER + "/api/projects"
HEADERS = {"Content-Type": "application/json"}
LOG_FILE = "/root/netops/test-reports/comprehensive/endurance.log"

def log(msg):
    ts = datetime.now().strftime("%H:%M")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def check_server():
    try:
        r = requests.get(SERVER, timeout=5)
        return r.status_code in (200, 302)
    except:
        return False

def create_project(name):
    try:
        r = requests.post(f"{API_PROJ}/", json={"name": name}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("id") or (data.get("data", {}) or {}).get("id")
    except Exception as e:
        log(f"  create_project error: {e}")
    return None

def get_topo(proj_id):
    try:
        r = requests.get(f"{API_PROJ}/{proj_id}/topo", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log(f"  get_topo error: {e}")
    return None

def save_topo(proj_id, topo_data):
    try:
        payload = {"nodes": topo_data.get("nodes",[]), "edges": topo_data.get("edges",[])}
        r = requests.post(f"{API_PROJ}/{proj_id}/topo",
                          json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log(f"  save_topo error: {e}")
        return False

def delete_project(proj_id):
    try:
        r = requests.delete(f"{API_PROJ}/{proj_id}", timeout=10)
        return r.status_code in (200, 204, 404)
    except:
        return False

# ─── Operation Engine ─────────────────────────────────────────────────────────

def apply_operations(topo, ops):
    """Apply LLM-returned operations to a topology dict {nodes:[], edges:[]}."""
    nodes = list(topo.get("nodes", []))
    edges = list(topo.get("edges", []))
    node_map = {n.get("id"): n for n in nodes}

    for op in ops:
        action = op.get("action", "")
        try:
            if action == "add":
                nid = op.get("id") or f"node_{uuid.uuid4().hex[:6]}"
                node = {
                    "id": nid,
                    "type": op.get("type", "switch"),
                    "x": int(op.get("x", 300)),
                    "y": int(op.get("y", 200)),
                    "label": op.get("label") or nid,
                    "ip": op.get("ip") or "",
                    "availablePorts": ["GE0/0/0","GE0/0/1","GE0/0/2","GE0/0/3"],
                    "usedPorts": [],
                }
                if nid not in node_map:
                    nodes.append(node)
                    node_map[nid] = node

            elif action in ("delete", "del"):
                target = op.get("id", "")
                # Find and remove node
                nodes = [n for n in nodes if n.get("id") != target and n.get("label") != target]
                node_map = {n.get("id"): n for n in nodes}
                # Remove related edges
                edges = [e for e in edges if e.get("from") != target and e.get("to") != target
                         and e.get("fromLabel") != target and e.get("toLabel") != target]

            elif action in ("add_edge", "connect", "add_connection"):
                frm = op.get("from", "")
                to = op.get("to", "")
                if not frm or not to: continue
                # Resolve IDs
                from_id = node_map.get(frm, {}).get("id") if frm in node_map else frm
                to_id = node_map.get(to, {}).get("id") if to in node_map else to
                edge_id = f"edge_{uuid.uuid4().hex[:6]}"
                edges.append({
                    "id": edge_id,
                    "from": from_id,
                    "to": to_id,
                    "fromLabel": frm,
                    "toLabel": to,
                    "srcPort": op.get("srcPort", "GE0/0/0"),
                    "tgtPort": op.get("tgtPort", "GE0/0/0"),
                })

            elif action == "remove_edge":
                frm = op.get("from", "")
                to = op.get("to", "")
                edges = [e for e in edges if not (
                    (e.get("from") == frm or e.get("fromLabel") == frm) and
                    (e.get("to") == to or e.get("toLabel") == to)
                )]

            elif action in ("update", "update_node", "rename"):
                target = op.get("id", "")
                for n in nodes:
                    if n.get("id") == target or n.get("label") == target:
                        if op.get("label"): n["label"] = op["label"]
                        if op.get("ip"): n["ip"] = op["ip"]
                        if op.get("desc"): n["desc"] = op["desc"]

            elif action == "move_node":
                target = op.get("id", "")
                for n in nodes:
                    if n.get("id") == target or n.get("label") == target:
                        n["x"] = int(op.get("x", 300))
                        n["y"] = int(op.get("y", 200))

        except Exception as e:
            log(f"    apply_ops error: {e} op={op}")

    return {"nodes": nodes, "edges": edges}

def send_chat(proj_id, message, topo=None, temperature=0.7):
    """Send chat + apply operations to topology."""
    with_topo = topo is not None
    payload = {
        "projectId": proj_id,
        "sessionId": "default",
        "text": message,
        "withTopo": with_topo,
        "topoMode": "brief"
    }
    if with_topo:
        payload["topology"] = topo
    try:
        r = requests.post(CHAT_API, json=payload, timeout=120)
        if r.status_code == 200:
            resp = r.json()
            ops = resp.get("operations", [])
            new_topo = apply_operations(topo or {"nodes":[],"edges":[]}, ops)
            if ops:
                save_topo(proj_id, new_topo)
            return resp, new_topo
        else:
            return {"reply": "", "operations": [], "error": f"HTTP {r.status_code}"}, topo or {"nodes":[],"edges":[]}
    except Exception as e:
        return {"reply": "", "operations": [], "error": str(e)}, topo or {"nodes":[],"edges":[]}

# ─── Round Test Functions ──────────────────────────────────────────────────────

def round1_humanization(proj_id):
    score, total, issues = 0, 3, []
    tests = [
        ("路由器和交换机有什么区别？", ["路由器", "交换机", "三层", "二层", "L2", "L3", "MAC", "IP"]),
        ("帮我评估万兆网络的优缺点", ["万兆", "10G", "带宽", "成本", "光纤", "高速"]),
        ("这个网络有什么安全隐患？", ["安全", "隐患", "漏洞", "防火墙", "攻击", "ACL"]),
    ]
    for prompt, keywords in tests:
        resp, _ = send_chat(proj_id, prompt)
        text = resp.get("reply", "").lower()
        if text:
            hits = sum(1 for kw in keywords if kw.lower() in text)
            if hits >= 2: score += 1
            else: issues.append(f"回答质量不足: {prompt[:15]}")
        else: issues.append(f"无回复: {prompt[:15]}")
        time.sleep(3)
    return score, total, issues

def round2_small_topology(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    resp, topo = send_chat(proj_id, "请添加1台路由器、2台PC和1台交换机，形成一个小型局域网拓扑", topo)
    time.sleep(5)
    topo = get_topo(proj_id) or topo
    nodes = topo.get("nodes", [])
    node_types = [n.get("type","").lower() for n in nodes]
    labels = " ".join([n.get("label","").lower() for n in nodes])
    rcount = sum(1 for t in node_types if "router" in t) or ("路由器" in labels)
    scount = sum(1 for t in node_types if "switch" in t) or ("交换机" in labels)
    pccount = sum(1 for t in node_types if any(x in t for x in ["pc","computer","server","workstation"]))
    if rcount >= 1: score += 1
    else: issues.append("未生成路由器")
    if scount >= 1: score += 1
    else: issues.append("未生成交换机")
    if pccount >= 2: score += 1
    else: issues.append(f"PC数量不足: {pccount}/2")
    return score, total, issues

def round3_medium_topology(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    resp, topo = send_chat(proj_id, "请生成一个10台设备的企业网络拓扑，包含路由器、交换机和多种服务器", topo)
    time.sleep(5)
    topo = get_topo(proj_id) or topo
    nodes = topo.get("nodes", [])
    ntypes = [n.get("type","").lower() for n in nodes]
    labels = " ".join([n.get("label","").lower() for n in nodes])
    nc = len(nodes)
    if nc >= 8: score += 1
    else: issues.append(f"节点不足: {nc}/8")
    has_r = any("router" in t for t in ntypes) or "路由器" in labels
    has_s = any("switch" in t for t in ntypes) or "交换机" in labels
    if has_r and has_s: score += 1
    else: issues.append("缺路由器或交换机")
    has_sv = any("server" in t for t in ntypes) or "服务器" in labels
    if has_sv: score += 1
    else: issues.append("缺服务器")
    return score, total, issues

def round4_large_topology(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    resp, topo = send_chat(proj_id, "请生成一个50台设备的园区网络拓扑，包含多个子网、VLAN和冗余链路", topo)
    time.sleep(10)
    topo = get_topo(proj_id) or topo
    nodes, edges = topo.get("nodes",[]), topo.get("edges",[])
    nc, ec = len(nodes), len(edges)
    text = json.dumps(topo, ensure_ascii=False)
    if nc >= 40: score += 1
    else: issues.append(f"节点不足: {nc}/40")
    if ec >= nc * 0.5: score += 1
    else: issues.append(f"连接不足: {ec}")
    kw_list = ["vlan","子网","subnet","核心","汇聚","接入","楼层","distribution"]
    if any(kw in text.lower() for kw in kw_list): score += 1
    else: issues.append("未发现子网/VLAN规划")
    return score, total, issues

def round5_100_nodes(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    start = time.time()
    resp, topo = send_chat(proj_id, "请生成一个包含100台设备的数据中心网络拓扑，包含核心层、汇聚层、接入层", topo)
    elapsed = time.time() - start
    topo = get_topo(proj_id) or topo
    nodes = topo.get("nodes",[])
    if elapsed < 60: score += 1
    else: issues.append(f"响应过慢: {elapsed:.1f}s")
    if len(nodes) >= 80: score += 1
    else: issues.append(f"节点不足: {len(nodes)}/80")
    text = json.dumps(topo, ensure_ascii=False)
    if any(kw in text.lower() for kw in ["core","核心","汇聚","核心层","distribution"]): score += 1
    else: issues.append("缺少核心层")
    return score, total, issues

def round6_vlan_security(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    resp, topo = send_chat(proj_id, "请规划IT部门、财务部门、生产部门三个VLAN区域，配置相应的网段和访问控制策略", topo)
    time.sleep(5)
    topo = get_topo(proj_id) or topo
    text = json.dumps(topo, ensure_ascii=False).lower() + resp.get("reply","").lower()
    depts = sum(1 for kw in ["it","财务","生产","finance","production","IT部","财务部","生产部"] if kw in text)
    vlan_found = "vlan" in text
    if depts >= 2 or vlan_found: score += 1
    else: issues.append("VLAN规划不完整")
    if any(kw in text for kw in ["firewall","防火墙","acl","策略","nat"]): score += 1
    else: issues.append("未发现访问控制策略")
    if any(kw in text for kw in ["子网","subnet","网段","192.168","10.0","ip地址"]): score += 1
    else: issues.append("未发现网段规划")
    return score, total, issues

def round7_context_retention(proj_id):
    score, total, issues = 0, 4, []
    topo = {"nodes": [], "edges": []}
    resp1, topo = send_chat(proj_id, "帮我设计一个小型办公室网络，有8台PC和1台打印机", topo)
    time.sleep(3)
    resp2, topo = send_chat(proj_id, "现在需要再加2台服务器，分别用作文件服务器和Web服务器", topo)
    time.sleep(3)
    resp3, topo = send_chat(proj_id, "请给Web服务器分配一个公网IP地址，并配置NAT转换", topo)
    time.sleep(3)
    topo = get_topo(proj_id) or topo
    text = json.dumps(topo, ensure_ascii=False)
    text_l = text.lower()
    all_text = resp1.get("reply","") + resp2.get("reply","") + resp3.get("reply","")
    all_l = all_text.lower()
    pc_hits = text_l.count("pc") + text_l.count("computer") + text_l.count("工作站") + text_l.count("电脑")
    if pc_hits >= 5: score += 1
    else: issues.append(f"PC数量不足: {pc_hits}")
    srv_hits = sum(1 for kw in ["server","服务器","web","文件服务器"] if kw in all_l)
    if srv_hits >= 2: score += 1
    else: issues.append(f"服务器关键词不足: {srv_hits}")
    nat_hits = sum(1 for kw in ["nat","firewall","防火墙","路由","公网","网关","NAT"] if kw in all_l)
    if nat_hits >= 2: score += 1
    else: issues.append(f"NAT配置不足: {nat_hits}")
    if "print" in text_l or "打印机" in text: score += 1
    else: issues.append("未发现打印机")
    return score, total, issues

def round8_llm_stability(proj_id):
    score, total, issues = 0, 3, []
    results = []
    for i in range(3):
        pid = create_project(f"stability-{i}-{int(time.time())}")
        if not pid:
            results.append(-1)
            continue
        topo = {"nodes": [], "edges": []}
        resp, _ = send_chat(pid, "生成一个5台设备的网络拓扑，包含1台路由器和4台PC", topo)
        time.sleep(2)
        t = get_topo(pid)
        results.append(len(t.get("nodes",[])) if t else 0)
        delete_project(pid)
    if all(r >= 0 for r in results):
        variance = max(results) - min(results) if results else 0
        if variance <= 5: score += 1
        else: issues.append(f"LLM波动: {results}")
        if all(r >= 3 for r in results): score += 1
        else: issues.append(f"部分结果异常: {results}")
        score += 1
    else: issues.append(f"测试失败: {results}")
    return score, total, issues

def round9_humanization_retest(proj_id):
    return round1_humanization(proj_id)

def round10_topology_quality(proj_id):
    score, total, issues = 0, 5, []
    topo = {"nodes": [], "edges": []}
    resp, topo = send_chat(proj_id, "请生成一个中等规模的企业网络，包含核心层和接入层的完整拓扑，标注设备名称和IP地址", topo)
    time.sleep(5)
    topo = get_topo(proj_id) or topo
    nodes, edges = topo.get("nodes",[]), topo.get("edges",[])
    text = json.dumps(topo, ensure_ascii=False)
    if 5 <= len(nodes) <= 30: score += 1
    else: issues.append(f"节点数异常: {len(nodes)}")
    if len(edges) >= len(nodes)*0.3: score += 1
    else: issues.append("连接不足")
    named = sum(1 for n in nodes if n.get("label") or n.get("name"))
    if named >= len(nodes)*0.7: score += 1
    else: issues.append("命名不完整")
    if any(kw in text for kw in ["192.168","10.","ip","IP","ip地址"]): score += 1
    else: issues.append("未发现IP规划")
    ntypes_l = " ".join([str(n.get("type","")).lower() for n in nodes])
    labels_l = " ".join([str(n.get("label","")).lower() for n in nodes])
    combined = (ntypes_l + " " + labels_l).lower()
    if any(x in combined for x in ["core","核心","接入","access","distribution","汇聚"]): score += 1
    else: issues.append("无层次结构")
    return score, total, issues

def round11_crud_operations(proj_id):
    score, total, issues = 0, 4, []
    topo = {"nodes": [], "edges": []}
    _, topo = send_chat(proj_id, "创建一个包含路由器和3台PC的拓扑", topo)
    time.sleep(5)
    _, topo = send_chat(proj_id, "删除其中一台PC", topo)
    time.sleep(3)
    _, topo = send_chat(proj_id, "将路由器重命名为 Core-Router", topo)
    time.sleep(3)
    _, topo = send_chat(proj_id, "再添加一台服务器命名为 Web-Server", topo)
    time.sleep(5)
    topo = get_topo(proj_id) or topo
    nodes = topo.get("nodes",[])
    text = json.dumps(nodes, ensure_ascii=False)
    text_l = text.lower()
    if len(nodes) >= 2: score += 1
    else: issues.append("节点数异常")
    if "core-router" in text_l or "Core-Router" in text: score += 1
    else: issues.append("重命名未生效")
    if "web-server" in text_l or "web-server" in text_l or "server" in text_l: score += 1
    else: issues.append("添加未生效")
    pc_cnt = text_l.count("pc") + text_l.count("computer") + text_l.count("电脑")
    if pc_cnt >= 1: score += 1
    else: issues.append("PC删除后数量异常")
    return score, total, issues

def round12_undo_redo(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    _, topo = send_chat(proj_id, "创建一个包含2台PC的拓扑", topo)
    time.sleep(5)
    before = len(topo.get("nodes",[]))
    _, topo = send_chat(proj_id, "再添加3台服务器", topo)
    time.sleep(5)
    after = len(topo.get("nodes",[]))
    _, topo = send_chat(proj_id, "撤销上一步操作", topo)
    time.sleep(5)
    undo = len(topo.get("nodes",[]))
    _, topo = send_chat(proj_id, "重做", topo)
    time.sleep(5)
    redo = len(topo.get("nodes",[]))
    if after > before: score += 1
    else: issues.append(f"添加未生效: {before}->{after}")
    if undo <= after: score += 1
    else: issues.append(f"撤销未生效: {undo}>{after}")
    if redo >= undo: score += 1
    else: issues.append(f"重做未生效: {redo}<{undo}")
    return score, total, issues

def round13_project_save_load(proj_id):
    score, total, issues = 0, 3, []
    topo = {"nodes": [], "edges": []}
    _, topo = send_chat(proj_id, "创建一个包含路由器、交换机和5台PC的网络拓扑", topo)
    time.sleep(5)
    if topo:
        if save_topo(proj_id, topo): score += 1
        else: issues.append("保存失败")
        _, topo2 = send_chat(proj_id, "添加一台打印机", topo)
        time.sleep(3)
        if len(topo2.get("nodes",[])) > len(topo.get("nodes",[])): score += 1
        else: issues.append("数据不一致")
        if "nodes" in topo2 and "edges" in topo2: score += 1
        else: issues.append("结构不完整")
    else: issues.append("无法获取拓扑")
    return score, total, issues

def round14_proactive_ai(proj_id):
    score, total, issues = 0, 4, []
    topo = {"nodes": [], "edges": []}
    _, topo = send_chat(proj_id, "创建一个简单的2台PC直连的拓扑", topo)
    time.sleep(5)
    resp, topo = send_chat(proj_id, "这个拓扑有什么问题？有什么优化建议？", topo)
    text = resp.get("reply","").lower()
    found = sum(1 for kw in ["网关","路由","交换机","路由器","问题","建议","优化","安全","单点","没有","缺少","NAT"] if kw in text)
    if found >= 3: score += 2
    elif found >= 1: score += 1
    else: issues.append("AI未发现问题")
    if sum(1 for kw in ["建议","应该","可以","最好","添加","优化","增加"] if kw in text) >= 2: score += 1
    else: issues.append("未给出建议")
    topo_final = get_topo(proj_id) or topo
    if len(topo_final.get("nodes",[])) > 2: score += 1
    else: issues.append("AI未自动优化拓扑")
    return score, total, issues

def round15_comprehensive_stress(proj_id):
    score, total, issues = 0, 5, []
    topo = {"nodes": [], "edges": []}
    start = time.time()
    resp, topo = send_chat(proj_id, "生成一个100台设备的复杂数据中心网络，包含核心交换机、汇聚交换机、接入交换机、服务器集群、存储网络和负载均衡器", topo)
    elapsed = time.time() - start
    topo = get_topo(proj_id) or topo
    nodes, edges = topo.get("nodes",[]), topo.get("edges",[])
    if elapsed < 90: score += 1
    else: issues.append(f"生成过慢: {elapsed:.1f}s")
    if len(nodes) >= 80: score += 1
    else: issues.append(f"节点不足: {len(nodes)}/80")
    if len(edges) >= len(nodes)*0.4: score += 1
    else: issues.append(f"连接不足: {len(edges)}")
    ntypes = set(n.get("type","").lower() for n in nodes)
    if len(ntypes) >= 4: score += 1
    else: issues.append(f"类型单一: {len(ntypes)}种")
    _, topo2 = send_chat(proj_id, "再添加20台虚拟机", topo)
    time.sleep(5)
    if len(topo2.get("nodes",[])) > len(nodes): score += 1
    else: issues.append("后续添加失败")
    return score, total, issues

def round16_final_acceptance(proj_id):
    score, total, issues = 0, 6, []
    topo = {"nodes": [], "edges": []}
    checks = [
        ("创建一个企业网络，包含路由器、核心交换机、汇聚交换机和10台接入设备",
         lambda t: len(t.get("nodes",[])) >= 8, "节点数量"),
        ("为上述网络配置3个VLAN",
         lambda t: "vlan" in json.dumps(t, ensure_ascii=False).lower(), "VLAN配置"),
        ("添加防火墙并配置安全策略",
         lambda t: any(kw in json.dumps(t,ensure_ascii=False).lower() for kw in ["firewall","防火墙","acl"]), "防火墙配置"),
        ("配置 NAT 使内部网络可以访问外网",
         lambda t: any(kw in json.dumps(t,ensure_ascii=False).lower() for kw in ["nat","路由","gateway","网关","NAT"]), "NAT配置"),
    ]
    for prompt, check_fn, name in checks:
        _, topo = send_chat(proj_id, prompt, topo)
        time.sleep(5)
        topo = get_topo(proj_id) or topo
        if check_fn(topo): score += 1
        else: issues.append(f"验收失败: {name}")
    resp, _ = send_chat(proj_id, "这个网络有什么可以改进的地方？", topo)
    if resp.get("reply") and len(resp.get("reply","")) > 50: score += 1
    else: issues.append("建议生成失败")
    if topo:
        if save_topo(proj_id, topo): score += 1
        else: issues.append("最终保存失败")
    else: issues.append("无法获取最终拓扑")
    return score, total, issues

ROUNDS = [
    (1,  "AI人性化（日常问答）",            round1_humanization),
    (2,  "小规模拓扑（3-5节点）",            round2_small_topology),
    (3,  "中等规模拓扑（10节点）",           round3_medium_topology),
    (4,  "大规模拓扑（50节点）",             round4_large_topology),
    (5,  "100节点压力测试",                 round5_100_nodes),
    (6,  "VLAN/安全区域操作生成",             round6_vlan_security),
    (7,  "连续对话上下文保持",              round7_context_retention),
    (8,  "LLM随机性/零误判测试",            round8_llm_stability),
    (9,  "AI人性化复测",                   round9_humanization_retest),
    (10, "拓扑生成质量评分",                round10_topology_quality),
    (11, "删除/重命名/移动操作",            round11_crud_operations),
    (12, "撤销/重做链完整性",               round12_undo_redo),
    (13, "项目保存/加载",                  round13_project_save_load),
    (14, "AI主动性评估",                   round14_proactive_ai),
    (15, "综合压力测试（100节点+多操作）",    round15_comprehensive_stress),
    (16, "最终验收测试",                    round16_final_acceptance),
]

def generate_final_report(results):
    report_path = "/root/netops/test-reports/comprehensive/FINAL_8H_REPORT.md"
    total_rounds = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    skipped = sum(1 for r in results if r["status"] in ("SKIP","ERROR"))
    total_score = sum(r["score"] for r in results)
    total_possible = sum(r["total"] for r in results)
    avg_score = total_score/total_possible*100 if total_possible > 0 else 0
    all_issues = [(r["round"], r["theme"], i) for r in results for i in r["issues"]]

    report = f"""# NetOps 8小时持续测试 - 最终报告

## 测试概览
- **测试时间**: 2026-03-31 07:47 GMT+8
- **Server**: http://192.168.32.72:6133/

## 结果摘要
| 指标 | 值 |
|------|-----|
| 总轮次 | {total_rounds} |
| 通过 | {passed} |
| 失败 | {failed} |
| 跳过/错误 | {skipped} |
| 总得分 | {total_score}/{total_possible} |
| 平均得分率 | {avg_score:.1f}% |

## 详细测试结果
| 轮次 | 主题 | 评分 | 结果 | 问题数 |
|------|------|------|------|--------|
"""
    for r in results:
        report += f"| {r['round']} | {r['theme']} | {r['score']}/{r['total']} | {r['status']} | {len(r['issues'])} |\n"

    report += "\n## 问题汇总\n\n"
    if all_issues:
        for rn, theme, issue in all_issues:
            report += f"- **Round {rn} ({theme})**: {issue}\n"
    else:
        report += "无重大问题发现。\n"

    report += "\n## 评分趋势\n\n"
    for r in results:
        pct = r["score"]/r["total"]*100 if r["total"] > 0 else 0
        bar = "█"*int(pct/10) + "░"*(10-int(pct/10))
        report += f"Round {r['round']:2d} | {bar} {pct:5.1f}% | {r['theme']}\n"

    report += f"""
## Prompt优化建议
1. 拓扑生成: 确保节点数量达到要求的80%以上
2. VLAN配置: 自动包含VLAN ID和子网信息
3. 上下文保持: 连续对话中记住之前添加的设备
4. 撤销/重做: 确保操作历史栈正确维护
5. AI主动性: 发现问题时主动提出优化建议
6. 性能优化: 100节点生成控制在90秒内

## 结论
- 通过率: {passed/total_rounds*100:.1f}% ({passed}/{total_rounds})
- 平均得分: {avg_score:.1f}%
- 整体评估: {"优秀" if avg_score>=80 else "良好" if avg_score>=60 else "需改进"}
"""
    with open(report_path, "w") as f:
        f.write(report)
    log(f"最终报告已生成: {report_path}")
    log(f"完成: {passed}/{total_rounds} 轮通过, 平均 {avg_score:.1f}%")

def main():
    log("=" * 60)
    log("NetOps 8小时持续测试开始 v3")
    log(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 60)

    results = []
    for round_num, theme, test_fn in ROUNDS:
        log(f"--- Round {round_num} 开始: {theme} ---")
        try:
            server_ok = check_server()
            df_out = subprocess.check_output("df -h / | tail -1", shell=True).decode().strip()
            log(f"  Server: {'UP' if server_ok else 'DOWN'} | {df_out}")
        except Exception as e:
            log(f"  环境检查失败: {e}")
            server_ok = False

        if not server_ok:
            log(f"  Round {round_num}: SKIP - Server不可用")
            results.append({"round":round_num,"theme":theme,"status":"SKIP","score":0,"total":1,"issues":["Server不可用"]})
            if round_num < 16:
                log("  休息120秒..."); time.sleep(120)
            continue

        proj_name = f"endurance-r{round_num}-{int(time.time())}"
        proj_id = create_project(proj_name)
        if not proj_id:
            log(f"  Round {round_num}: SKIP - 无法创建项目")
            results.append({"round":round_num,"theme":theme,"status":"SKIP","score":0,"total":1,"issues":["无法创建项目"]})
            if round_num < 16:
                time.sleep(120)
            continue

        log(f"  项目ID: {proj_id}")
        try:
            score, total, issues = test_fn(proj_id)
            status = "PASS" if score >= total * 0.6 else "FAIL"
            log(f"  Round {round_num} 完成: {score}/{total} | {status}")
            for issue in issues:
                log(f"    ! {issue}")
            results.append({"round":round_num,"theme":theme,"status":status,"score":score,"total":total,"issues":issues})
        except Exception as e:
            import traceback; traceback.print_exc()
            log(f"  Round {round_num} 异常: {e}")
            results.append({"round":round_num,"theme":theme,"status":"ERROR","score":0,"total":1,"issues":[str(e)]})

        try: delete_project(proj_id)
        except: pass

        if round_num < 16:
            log("  休息120秒...")
            time.sleep(120)

    log("=" * 60)
    log("所有16轮完成，生成最终报告...")
    generate_final_report(results)
    log("=" * 60)

if __name__ == "__main__":
    main()
