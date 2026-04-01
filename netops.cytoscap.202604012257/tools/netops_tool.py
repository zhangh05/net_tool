#!/usr/bin/env python3
"""
NetOps 客户端工具
TOPO Agent 通过此脚本与 NetOps 服务通信

用法：
  python3 netops_tool.py <command> [args...]

命令：
  get-topology                          获取当前拓扑（从JSON文件）
  add-device <type> <label> [ip] [x] [y]  添加设备
  remove-node <id_or_label>            删除节点
  rename-node <old_label> <new_label>  重命名节点
  add-edge <src> <tgt> [src_port] [tgt_port] [bandwidth]  添加连线
  remove-edge <src> <tgt>             删除连线
  ping <host> [source_addr]            执行 Ping（异步，调用后等待）
  read-ping <sid>                     读取 Ping 结果
  chat <message>                      发送 AI 对话
  describe-topology                    分析并描述拓扑
"""
import sys
import json
import urllib.request
import urllib.error
import os
import time

BASE_URL = "http://127.0.0.1:6133"
SRC_ADDR = "192.168.32.72"


def api_get(path):
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def api_post(path, data):
    try:
        req = urllib.request.Request(
            BASE_URL + path,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def get_topology():
    """通过 API 读取当前拓扑"""
    return api_get("/api/topo")

def get_topology_direct():
    """直接读取文件（daemon 专用，避免 HTTP 死锁）"""
    topo_file = os.environ.get(
        'NETOPS_TOPO_FILE',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'netops', 'current_topology.json')
    )
    topo_file = os.path.normpath(topo_file)
    try:
        if os.path.exists(topo_file):
            with open(topo_file, encoding='utf-8') as f:
                return json.load(f)
        return {"nodes": [], "edges": []}
    except Exception as e:
        return {"error": str(e)}


# ========== 文件操作（仅 uploads 目录） ==========
def list_uploads():
    """列出 uploads 目录下的文件"""
    return api_get("/api/uploads/list")


def read_upload(filename):
    """读取 uploads 目录下的指定文件"""
    return api_get(f"/api/uploads/read?file={urllib.parse.quote(filename)}")


def save_topology(data):
    """通过 API 保存拓扑"""
    return api_post("/api/topo", data)

def save_topology_direct(data):
    """直接写文件（daemon 专用）"""
    topo_file = os.environ.get(
        'NETOPS_TOPO_FILE',
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'netops', 'current_topology.json')
    )
    topo_file = os.path.normpath(topo_file)
    try:
        with open(topo_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return {"status": "ok"}
    except Exception as e:
        return {"error": str(e)}


def add_device(dtype, label, ip="", x=300, y=300):
    topo = get_topology_direct()
    if "error" in topo:
        return topo
    nodes = topo.get("nodes", [])

    # 生成唯一 ID
    existing_ids = [n.get("id", "") for n in nodes]
    nid = label.lower().replace(" ", "-")
    cnt = 1
    while nid in existing_ids:
        cnt += 1
        nid = f"{label.lower().replace(' ', '-')}-{cnt}"

    # 设备图标
    icon_map = {
        "router": "./icons/router.png", "switch": "./icons/switch.png",
        "firewall": "./icons/firewall.png", "server": "./icons/server.png", "pc": "./icons/pc.png"
    }
    icon = icon_map.get(dtype, "")

    new_node = {
        "id": nid, "label": label, "type": dtype,
        "ip": ip, "x": x, "y": y, "w": 80, "h": 80,
        "color": "#3b82f6",
        **({"icon": icon} if icon else {})
    }
    nodes.append(new_node)
    topo["nodes"] = nodes
    result = save_topology_direct(topo)
    if result.get("status") == "ok":
        return {"status": "ok", "node": new_node}
    return result


def remove_node(id_or_label):
    topo = get_topology_direct()
    if "error" in topo:
        return topo
    nodes = topo.get("nodes", [])
    edges = topo.get("edges", [])

    # 查找节点
    found = None
    for n in nodes:
        if n.get("id") == id_or_label or n.get("label") == id_or_label:
            found = n
            break

    if not found:
        return {"status": "error", "message": f"未找到节点：{id_or_label}"}

    nid = found["id"]
    topo["nodes"] = [n for n in nodes if n["id"] != nid]
    topo["edges"] = [e for e in edges if e.get("src") != nid and e.get("tgt") != nid]
    return save_topology_direct(topo)


def rename_node(old_label, new_label):
    topo = get_topology_direct()
    if "error" in topo:
        return topo
    found = False
    for n in topo.get("nodes", []):
        if n.get("label") == old_label:
            n["label"] = new_label
            found = True
    if not found:
        return {"status": "error", "message": f"未找到：{old_label}"}
    return save_topology_direct(topo)


def add_edge(src_label, tgt_label, src_port="", tgt_port="", bandwidth=""):
    topo = get_topology_direct()
    if "error" in topo:
        return topo

    # 查找节点 ID
    src_id = None
    tgt_id = None
    for n in topo.get("nodes", []):
        if n.get("label") == src_label:
            src_id = n["id"]
        if n.get("label") == tgt_label:
            tgt_id = n["id"]

    if not src_id:
        return {"status": "error", "message": f"未找到源节点：{src_label}"}
    if not tgt_id:
        return {"status": "error", "message": f"未找到目标节点：{tgt_label}"}

    edge_id = f"e-{src_id}-{tgt_id}"
    topo.setdefault("edges", []).append({
        "id": edge_id, "src": src_id, "tgt": tgt_id,
        "srcPort": src_port, "tgtPort": tgt_port, "bandwidth": bandwidth
    })
    return save_topology_direct(topo)


def remove_edge(src_label, tgt_label):
    topo = get_topology_direct()
    if "error" in topo:
        return topo

    src_id = None
    tgt_id = None
    for n in topo.get("nodes", []):
        if n.get("label") == src_label:
            src_id = n["id"]
        if n.get("label") == tgt_label:
            tgt_id = n["id"]

    if not src_id or not tgt_id:
        return {"status": "error", "message": f"未找到节点"}

    topo["edges"] = [
        e for e in topo.get("edges", [])
        if not (e.get("src") == src_id and e.get("tgt") == tgt_id)
    ]
    return save_topology_direct(topo)


def ping(host, source_addr=SRC_ADDR):
    return api_post("/api/ping/start", {"host": host, "source_addr": source_addr})


def read_ping(sid):
    return api_get(f"/api/ping/read?sid={sid}")


def chat(message):
    return api_post("/api/chat/send", {"message": message})


def describe_topology(topo=None):
    """分析拓扑结构，返回自然语言描述。topo 为空时自动获取"""
    if topo is None:
        topo = get_topology()
    if "error" in topo:
        return f"❌ 获取拓扑失败：{topo['error']}"

    nodes = topo.get("nodes", [])
    edges = topo.get("edges", [])

    devices = [n for n in nodes if not n.get("isShape") and not n.get("isTextBox")]
    shapes = [n for n in nodes if n.get("isShape")]
    texts = [n for n in nodes if n.get("isTextBox")]

    result_lines = []
    result_lines.append(f"📊 拓扑概览：")
    result_lines.append(f"  设备：{len(devices)} 台")
    result_lines.append(f"  形状：{len(shapes)} 个")
    result_lines.append(f"  文本框：{len(texts)} 个")
    result_lines.append(f"  连线：{len(edges)} 条")

    if devices:
        by_type = {}
        for d in devices:
            t = d.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        result_lines.append(f"\n  设备类型分布：")
        type_names = {"router": "路由器", "switch": "交换机", "firewall": "防火墙",
                       "server": "服务器", "pc": "PC"}
        for t, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            name = type_names.get(t, t)
            result_lines.append(f"    {name}：{cnt} 台")

        with_ip = [d for d in devices if d.get("ip")]
        if with_ip:
            result_lines.append(f"\n  已配置 IP 的设备：")
            for d in with_ip[:10]:
                result_lines.append(f"    {d.get('label','?')} ({d.get('type','?')}): {d.get('ip','无IP')}")
            if len(with_ip) > 10:
                result_lines.append(f"    ... 还有 {len(with_ip)-10} 台")

    if edges and devices:
        result_lines.append(f"\n  连线：{len(edges)} 条")
        for e in edges[:5]:
            src = next((d.get("label","?") for d in devices if d.get("id") == e.get("src")), "?")
            tgt = next((d.get("label","?") for d in devices if d.get("id") == e.get("tgt")), "?")
            bw = e.get("bandwidth", "")
            result_lines.append(f"    {src} → {tgt}" + (f" ({bw})" if bw else ""))
        if len(edges) > 5:
            result_lines.append(f"    ... 还有 {len(edges)-5} 条")

    if shapes:
        result_lines.append(f"\n  形状标注：")
        for s in shapes[:5]:
            t = "矩形" if s.get("type") == "rectangle" else "椭圆"
            result_lines.append(f"    [{t}] {s.get('label') or '(无文字)'}")
        if len(shapes) > 5:
            result_lines.append(f"    ... 还有 {len(shapes)-5} 个")

    if not devices and not shapes:
        result_lines.append(f"\n  ⚠ 当前拓扑为空，可以开始规划！")

    return "\n".join(result_lines)


# ========== 命令行入口 ==========
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    result = None

    try:
        if cmd == "get-topology":
            result = get_topology()
        elif cmd == "add-device" and len(sys.argv) >= 4:
            dtype = sys.argv[2]
            label = sys.argv[3]
            ip = sys.argv[4] if len(sys.argv) > 4 else ""
            x = int(sys.argv[5]) if len(sys.argv) > 5 else 300
            y = int(sys.argv[6]) if len(sys.argv) > 6 else 300
            result = add_device(dtype, label, ip, x, y)
        elif cmd == "remove-node" and len(sys.argv) >= 3:
            result = remove_node(sys.argv[2])
        elif cmd == "rename-node" and len(sys.argv) >= 4:
            result = rename_node(sys.argv[2], sys.argv[3])
        elif cmd == "add-edge" and len(sys.argv) >= 4:
            src = sys.argv[2]
            tgt = sys.argv[3]
            src_port = sys.argv[4] if len(sys.argv) > 4 else ""
            tgt_port = sys.argv[5] if len(sys.argv) > 5 else ""
            bw = sys.argv[6] if len(sys.argv) > 6 else ""
            result = add_edge(src, tgt, src_port, tgt_port, bw)
        elif cmd == "remove-edge" and len(sys.argv) >= 4:
            result = remove_edge(sys.argv[2], sys.argv[3])
        elif cmd == "ping" and len(sys.argv) >= 3:
            src = sys.argv[3] if len(sys.argv) > 3 else SRC_ADDR
            result = ping(sys.argv[2], src)
        elif cmd == "read-ping" and len(sys.argv) >= 3:
            result = read_ping(sys.argv[2])
        elif cmd == "chat" and len(sys.argv) >= 3:
            result = chat(" ".join(sys.argv[2:]))
        elif cmd == "describe-topology":
            print(describe_topology())
            sys.exit(0)
        else:
            print(__doc__)
            sys.exit(1)

        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
