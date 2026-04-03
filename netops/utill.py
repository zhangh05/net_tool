# utill - minimal HTTP+WebSocket utility
# Provides: ut.ws(WebSocketHandler, options) and ut.run()
import asyncio
import websockets
import threading
import http.server
import socketserver

class ws:
    def __init__(self, handler_class, options=None):
        self.handler_class = handler_class
        self.options = options or {}
        self.server = None
        self.thread = None

    async def _start_async(self, host, port):
        async def handler(websocket, path):
            h = self.handler_class()
            await h.handle(websocket, path)

        self.server = await websockets.serve(handler, host, port)
        await asyncio.Future()

    def run(self, host='0.0.0.0', port=9000):
        self.thread = threading.Thread(target=self._run_thread, args=(host, port), daemon=True)
        self.thread.start()

    def _run_thread(self, host, port):
        asyncio.run(self._start_async(host, port))

    def _run_sync(self, host, port):
        asyncio.run(self._start_async(host, port))

ut = type('ut', (), {'ws': ws, 'run': lambda self, host='0.0.0.0', port=9000: threading.Thread(target=lambda: asyncio.run(self._start_async(host, port)), daemon=True).start()})()
