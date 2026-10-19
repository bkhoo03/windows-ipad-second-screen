"""
iPad second-screen streaming server.

Two servers run together:
  1. A tiny HTTP server that serves the client web page (client.html).
  2. A WebSocket server that streams JPEG frames of the chosen monitor.

Capture runs in a background thread (mss is blocking and thread-bound);
frames are handed to the asyncio side and broadcast to all connected clients.

Run:  python server.py
Then open  http://<your-pc-ip>:<HTTP_PORT>  in Safari on the iPad.
"""

import asyncio
import socket
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

import config
from capture import ScreenCapturer

CLIENT_HTML = Path(__file__).with_name("client.html")

# The WebSocket runs on the HTTP port + 1.
WS_PORT = config.PORT + 1


# --------------------------------------------------------------------------- #
# HTTP: serve the client page
# --------------------------------------------------------------------------- #
class ClientPageHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, ws_port: int, **kwargs):
        self._ws_port = ws_port
        super().__init__(*args, **kwargs)

    def do_GET(self):
        try:
            html = CLIENT_HTML.read_text(encoding="utf-8")
        except FileNotFoundError:
            self.send_error(404, "client.html not found")
            return

        # Inject the websocket port so the page knows where to connect.
        html = html.replace("__WS_PORT__", str(self._ws_port))
        body = html.encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # keep the console quiet


def start_http_server(host: str, port: int, ws_port: int):
    handler = partial(ClientPageHandler, ws_port=ws_port)
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((host, port), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


# --------------------------------------------------------------------------- #
# Capture -> frame hub
# --------------------------------------------------------------------------- #
class FrameHub:
    """Holds the latest frame and lets async clients wait for the next one."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._latest: bytes | None = None
        self._event = asyncio.Event()

    def publish_threadsafe(self, frame: bytes):
        self._loop.call_soon_threadsafe(self._set, frame)

    def _set(self, frame: bytes):
        self._latest = frame
        self._event.set()
        self._event.clear()

    async def wait_for_frame(self) -> bytes:
        await self._event.wait()
        return self._latest


def capture_loop(hub: FrameHub, stop: threading.Event):
    capturer = ScreenCapturer(
        monitor_index=config.MONITOR_INDEX,
        jpeg_quality=config.JPEG_QUALITY,
        max_width=config.MAX_WIDTH,
        target_fps=config.TARGET_FPS,
    )
    w, h = capturer.size
    print(f"[capture] streaming monitor index {config.MONITOR_INDEX} "
          f"({w}x{h}) at up to {config.TARGET_FPS} fps "
          f"[backend: {capturer.backend}]")

    frame_interval = 1.0 / max(1, config.TARGET_FPS)
    last_frame = None
    try:
        while not stop.is_set():
            start = time.perf_counter()
            try:
                frame = capturer.grab_jpeg()
                # Skip resending a byte-identical frame (static screen), which
                # saves bandwidth. Cursor moves / content changes still send.
                if frame is not None and frame != last_frame:
                    hub.publish_threadsafe(frame)
                    last_frame = frame
            except Exception as e:
                print(f"[capture] error: {e}")
                time.sleep(0.5)
                continue
            sleep_for = frame_interval - (time.perf_counter() - start)
            if sleep_for > 0:
                time.sleep(sleep_for)
    finally:
        capturer.close()


# --------------------------------------------------------------------------- #
# WebSocket: stream frames
# --------------------------------------------------------------------------- #
async def ws_handler(websocket, hub: FrameHub):
    peer = websocket.remote_address
    print(f"[ws] client connected: {peer}")
    try:
        while True:
            frame = await hub.wait_for_frame()
            await websocket.send(frame)
    except ConnectionClosed:
        pass
    except Exception as e:
        print(f"[ws] send error to {peer}: {e}")
    finally:
        print(f"[ws] client disconnected: {peer}")


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def get_tailscale_name() -> str | None:
    """Return the full Tailscale MagicDNS name of this machine, or None.

    This is the permanent address that works on any network. We query the
    Tailscale CLI; if it isn't installed/running, return None.
    """
    import subprocess
    import json

    ts = r"C:\Program Files\Tailscale\tailscale.exe"
    try:
        out = subprocess.run(
            [ts, "status", "--json"],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(out.stdout)
        name = (data.get("Self") or {}).get("DNSName", "")
        return name.rstrip(".") or None
    except Exception:
        return None


async def main():
    loop = asyncio.get_running_loop()
    hub = FrameHub(loop)
    stop = threading.Event()

    threading.Thread(target=capture_loop, args=(hub, stop), daemon=True).start()
    httpd = start_http_server(config.HOST, config.PORT, WS_PORT)

    ip = get_local_ip()
    ts_name = get_tailscale_name()
    print("=" * 64)
    print("  iPad second screen is running")
    if ts_name:
        print(f"  Permanent address (any WiFi):  http://{ts_name}:{config.PORT}")
    print(f"  Local address (same WiFi):     http://{ip}:{config.PORT}")
    print("  Open one of these in Safari on the iPad.")
    print("  Press Ctrl+C to stop.")
    print("=" * 64)

    async def handler(websocket):
        await ws_handler(websocket, hub)

    try:
        async with websockets.serve(
            handler,
            config.HOST,
            WS_PORT,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ):
            await asyncio.Future()  # run forever
    finally:
        stop.set()
        httpd.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
