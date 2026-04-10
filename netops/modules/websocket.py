# modules/websocket.py - WebSocket Server for real-time topology sync
import threading, asyncio, json

# ─── WebSocket Globals ──────────────────────────────────────────────────────────
WS_PORT = 9013
WS_AVAILABLE = False
ws_clients = set()
ws_topo_lock = threading.Lock()
ws_latest_topo = {}

# ─── WebSocket Functions ────────────────────────────────────────────────────────
def ws_broadcast(msg):
    if not WS_AVAILABLE or not ws_clients:
        return
    def _do_send():
        async def _send_all():
            msg_bytes = json.dumps(msg).encode('utf-8')
            for client in list(ws_clients):
                try:
                    await client.send(msg_bytes)
                except Exception:
                    ws_clients.discard(client)
        try:
            asyncio.run(_send_all())
        except Exception:
            pass
    t = threading.Thread(target=_do_send, daemon=True)
    t.start()

def ws_notify_topo_change(proj_id, topo):
    if not WS_AVAILABLE:
        return
    with ws_topo_lock:
        ws_latest_topo[proj_id] = topo
    ws_broadcast({'type': 'topo_update', 'project': proj_id, 'topo': topo})

async def ws_handler(websocket):
    ws_clients.add(websocket)
    proj_id = None
    try:
        try:
            path = websocket.request.path
        except AttributeError:
            path = str(websocket.path) if hasattr(websocket, 'path') else '/'
        parts = path.strip('/').split('/')
        if len(parts) >= 3 and parts[0] == 'ws' and parts[1] == 'topo':
            proj_id = parts[2]
        with ws_topo_lock:
            current = ws_latest_topo.get(proj_id, {})
        await websocket.send(json.dumps({'type': 'init', 'project': proj_id, 'topo': current}))
        async for msg in websocket:
            try:
                data = json.loads(msg)
                if data.get('type') == 'subscribe':
                    proj_id = data.get('project', proj_id)
                    with ws_topo_lock:
                        current = ws_latest_topo.get(proj_id, {})
                    await websocket.send(json.dumps({'type': 'init', 'project': proj_id, 'topo': current}))
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    finally:
        ws_clients.discard(websocket)

def start_ws_server():
    global WS_AVAILABLE
    try:
        import websockets
        WS_AVAILABLE = True
    except ImportError:
        WS_AVAILABLE = False
        print("[WebSocket] websockets library not found, real-time sync disabled")
        return

    async def run():
        try:
            async with websockets.serve(ws_handler, '0.0.0.0', WS_PORT):
                print(f'[WebSocket] Real-time sync server running on ws://0.0.0.0:{WS_PORT}')
                await asyncio.Future()
        except Exception as e:
            print(f'[WebSocket] Server error: {e}')

    def _runner():
        try:
            asyncio.run(run())
        except Exception as e:
            print(f'[WebSocket] Runner error: {e}')

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    print(f'[WebSocket] Starting real-time sync server on port {WS_PORT}...')
