# modules/terminal.py - PTY Terminal Session Management
import os, pty, fcntl, select, signal, struct, termios, threading, time, json, uuid, queue, signal, shutil
import asyncio

# ─── Terminal Session Globals ───────────────────────────────────────────────────
TERM_WS_PORT = 9011
_term_sessions = {}       # sid -> {'pid': int, 'master_fd': int, ...}
_term_active_ws = {}      # sid -> [websocket]
_term_sessions_lock = threading.Lock()
_term_session_queue = queue.Queue()

# ─── Session Manager Thread ────────────────────────────────────────────────────
def _term_session_manager_thread():
    """Background thread that creates/manages PTY sessions."""
    while True:
        task = _term_session_queue.get()
        if task is None:
            break
        action, data = task
        if action == 'create':
            sid, stype, ip, port, user, password = data
            _do_term_create_session(sid, stype, ip, port, user, password)
        elif action == 'kill':
            sid = data
            _do_term_kill_session(sid)

def _do_term_create_session(sid, stype, ip, port, user, password):
    """Create PTY session using forkpty."""
    try:
        m, s = pty.openpty()
        pid = os.fork()
        if pid == 0:
            os.close(m)
            try:
                import tty
                tty.setcontrollingterm(s)
            except Exception:
                pass
            os.setsid()
            try:
                fcntl.ioctl(s, termios.TIOCSCTTY, 0)
            except Exception:
                pass
            os.dup2(s, 0)
            os.dup2(s, 1)
            os.dup2(s, 2)
            if s > 2:
                os.close(s)
            env = dict(os.environ, TERM='xterm-256color', PS1='$ ')
            if stype == 'shell':
                os.execvpe('bash', ['bash', '-i'], env)
            elif stype == 'ssh':
                cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null']
                if password and shutil.which('sshpass'):
                    cmd = ['sshpass', '-p', password] + cmd
                if user:
                    cmd += ['-l', user]
                if port and str(port) not in ('22', ''):
                    cmd += ['-p', str(port)]
                cmd.append(ip)
                os.execvpe(cmd[0], cmd, env)
            elif stype == 'telnet':
                os.execvpe('sh', ['sh', '-c', f'telnet {ip} {port}'], env)
            else:
                os._exit(127)
        os.close(s)
        with _term_sessions_lock:
            _term_sessions[sid] = {'pid': pid, 'master_fd': m, 'ip': ip, 'port': str(port), 'protocol': stype, 'user': user, 'created_at': time.time()}

        def reader():
            try:
                while True:
                    try:
                        res = os.waitpid(pid, os.WNOHANG)
                        if res[0] != 0:
                            while True:
                                r, _, _ = select.select([m], [], [], 0.1)
                                if not r:
                                    break
                                d = os.read(m, 4096)
                                if not d:
                                    break
                                _term_broadcast(sid, d)
                            break
                    except ChildProcessError:
                        break
                    r, _, _ = select.select([m], [], [], 0.5)
                    if r:
                        d = os.read(m, 4096)
                        if not d:
                            break
                        _term_broadcast(sid, d)
            except Exception:
                pass
            finally:
                try:
                    os.close(m)
                except Exception:
                    pass
                with _term_sessions_lock:
                    _term_sessions.pop(sid, None)
                    _term_active_ws.pop(sid, None)

        t = threading.Thread(target=reader, daemon=True)
        t.start()
    except Exception as e:
        print(f'[Terminal] Failed to create session: {e}')

def _term_broadcast(sid, data):
    """Broadcast bytes to all WebSocket clients of a terminal session."""
    try:
        text = data.decode('utf-8', 'replace')
        msg = json.dumps({'type': 'output', 'data': text})
        ws_list = _term_active_ws.get(sid, [])
        for ws in list(ws_list):
            try:
                asyncio.run(ws.send(msg))
            except Exception:
                pass
    except Exception:
        pass

def _do_term_kill_session(sid):
    with _term_sessions_lock:
        info = _term_sessions.get(sid)
    if not info:
        return
    try:
        os.close(info['master_fd'])
    except Exception:
        pass
    try:
        os.kill(info['pid'], signal.SIGTERM)
        os.waitpid(info['pid'], 0)
    except Exception:
        pass
    with _term_sessions_lock:
        _term_sessions.pop(sid, None)
        _term_active_ws.pop(sid, None)

# ─── Terminal WebSocket Handler ────────────────────────────────────────────────
async def term_ws_handler(websocket):
    """Handle terminal WebSocket connections at /ws/<sid>."""
    try:
        path = websocket.request.path
    except AttributeError:
        path = str(websocket.path) if hasattr(websocket, 'path') else '/'
    sid = path.lstrip('/')
    if sid.startswith('ws/'):
        sid = sid[3:]

    with _term_sessions_lock:
        if sid not in _term_sessions:
            try:
                await websocket.send(json.dumps({'type': 'error', 'data': 'Session not found'}))
                await websocket.close()
            except Exception:
                pass
            return
        if sid not in _term_active_ws:
            _term_active_ws[sid] = []
        _term_active_ws[sid].append(websocket)

    try:
        async for msg in websocket:
            try:
                m = json.loads(msg)
            except Exception:
                continue
            with _term_sessions_lock:
                info = _term_sessions.get(sid)
            if not info:
                break
            if m.get('type') == 'input':
                data = m.get('data', '')
                if data:
                    try:
                        os.write(info['master_fd'], data.encode('utf-8'))
                    except Exception:
                        pass
            elif m.get('type') == 'resize':
                try:
                    fcntl.ioctl(info['master_fd'], termios.TIOCSWINSZ,
                                struct.pack('HHHH', m.get('rows', 24), m.get('cols', 80), 0, 0))
                except Exception:
                    pass
    except Exception:
        pass
    finally:
        with _term_sessions_lock:
            if sid in _term_active_ws and websocket in _term_active_ws[sid]:
                _term_active_ws[sid].remove(websocket)

def start_term_ws_server():
    """Start the terminal WebSocket server on port 9011."""
    try:
        import websockets
    except ImportError:
        print('[Terminal] websockets library not found')
        return

    async def run():
        try:
            async with websockets.serve(term_ws_handler, '0.0.0.0', TERM_WS_PORT):
                print(f'[Terminal] WebSocket server running on ws://0.0.0.0:{TERM_WS_PORT}')
                await asyncio.Future()
        except Exception as e:
            print(f'[Terminal] WebSocket server error: {e}')

    def _runner():
        try:
            asyncio.run(run())
        except Exception as e:
            print(f'[Terminal] WebSocket runner error: {e}')

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    print(f'[Terminal] Starting WebSocket server on port {TERM_WS_PORT}...')

# ─── Start manager thread ─────────────────────────────────────────────────────
_term_mgr_t = threading.Thread(target=_term_session_manager_thread, daemon=True)
_term_mgr_t.start()
print('[Terminal] Session manager thread started')
