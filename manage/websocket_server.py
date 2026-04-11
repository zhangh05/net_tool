#!/usr/bin/env python3
"""
Manage WebSocket Server - 实时推送进度和流式输出
端口: 9012
"""

import asyncio
import json
import threading
import time
from websockets.server import serve
import websockets

# 全局客户端集合
_clients = set()
_clients_lock = threading.Lock()


async def handle_client(websocket, path):
    """处理 WebSocket 客户端连接"""
    client_id = id(websocket)
    
    with _clients_lock:
        _clients.add(websocket)
    
    print(f"[WS] Client connected: {client_id}, total: {len(_clients)}")
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "ping":
                    await websocket.send(json.dumps({
                        "type": "pong", 
                        "time": time.time()
                    }))
            except json.JSONDecodeError:
                pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        with _clients_lock:
            _clients.discard(websocket)
        print(f"[WS] Client disconnected: {client_id}, total: {len(_clients)}")


def send_to_all(data):
    """向所有客户端广播消息（同步调用）"""
    if not _clients:
        return
    
    message = json.dumps(data, ensure_ascii=False)
    
    async def broadcast():
        disconnected = set()
        for client in _clients.copy():
            try:
                await client.send(message)
            except Exception as e:
                disconnected.add(client)
        with _clients_lock:
            for client in disconnected:
                _clients.discard(client)
    
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast())
        else:
            loop.run_until_complete(broadcast())
    except RuntimeError:
        asyncio.run(broadcast())


def broadcast_token(token):
    """广播 token（流式输出）"""
    send_to_all({
        "type": "token",
        "content": token
    })


def broadcast_stage(stage, substage=None, progress=0, message="", steps=None, result=None):
    """广播阶段更新（完整格式）
    
    stage:    'coord' | 'exec' | 'user'
    substage: 'analyzing' | 'planning' | 'dispatching' | 'executing' | 'summarizing' | ...
    progress: 0-100
    message:  当前状态文字
    steps:    [{id, text, status}]  步骤列表
    result:   {nodes, edges}  执行结果摘要
    """
    data = {
        "type": "stage",
        "stage": stage,
        "progress": progress,
        "time": time.time()
    }
    if substage:
        data["substage"] = substage
    if message:
        data["message"] = message
    if steps is not None:
        data["steps"] = steps
    if result is not None:
        data["result"] = result
    send_to_all(data)


def broadcast_layer_stage(layer, sub=None, progress=0, message="", agent=None, steps=None):
    """Broadcast a stage change for a specific layer (coord/netops).

    layer:    'coord' | 'netops'
    sub:      stage name within the layer (e.g. 'understanding', 'planning')
    progress: 0-100
    message:  current status text
    agent:   agent name
    steps:   list of step objects
    """
    data = {
        "type": "stage",
        "layer": layer,
        "stage": sub or layer,
        "progress": progress,
        "time": time.time()
    }
    if message:
        data["message"] = message
    if agent:
        data["agent"] = agent
    if steps is not None:
        data["steps"] = steps
    send_to_all(data)


def broadcast_done():
    """广播完成信号"""
    send_to_all({"type": "done"})


def broadcast_exec_step(step_num, total_steps, action, target, ok, message, seq=0):
    """实时推送执行步骤（逐条推送到前端）"""
    data = {
        "type": "exec_step",
        "step": step_num,
        "total": total_steps,
        "action": action,
        "target": target,
        "ok": ok,
        "message": message,
        "seq": seq,
        "time": time.time()
    }
    send_to_all(data)


def broadcast_plan(plan, task_id=None, goal_summary=None):
    """Broadcast execution plan to frontend for user confirmation.

    plan:         list of execution steps
    task_id:      optional task ID
    goal_summary: optional goal description
    """
    send_to_all({
        "type": "plan",
        "plan": plan,
        "task_id": task_id,
        "goal_summary": goal_summary,
        "time": time.time()
    })


def broadcast_progress(stage, message, steps=None, result=None):
    """
    广播进度更新（兼容旧接口）
    
    stage: thinking | dispatch | executing | complete | error
    """
    data = {
        "type": "progress",
        "stage": stage,
        "message": message,
        "time": time.time()
    }
    if steps is not None:
        data["steps"] = steps
    if result is not None:
        data["result"] = result
    
    send_to_all(data)


async def start_ws_server(port=9012):
    """启动 WebSocket 服务器"""
    async with serve(handle_client, "0.0.0.0", port):
        print(f"[WS] WebSocket server running on ws://0.0.0.0:{port}")
        await asyncio.Future()


def run_server(port=9012):
    """运行 WebSocket 服务器（阻塞）"""
    asyncio.run(start_ws_server(port))


def start_server_thread(port=9012):
    """在新线程中启动 WebSocket 服务器"""
    thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    thread.start()
    print(f"[WS] WebSocket server thread started on port {port}")
    return thread


if __name__ == "__main__":
    run_server(9012)
