"""
localhost HTTP server.

Default off; opt-in via Preferences. Only binds to 127.0.0.1 — never
LAN. For LAN / remote access, use WebRTC pairing (slice 1+).
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import api, bridge


_server = None
_server_thread = None


# CORS：浏览器从 AtlasMaker / WebPaint （不同 origin）调 BTP 必需。
# 仅本机服务 + 用户主动开启，允许 * 来源是安全的（其他网页要发请求得先有跨域权限，
# 而它们能拿到 localhost:18765 也是因为本机网络可达 —— CORS 不再是安全边界）。
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, PUT, POST, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, X-BTP-Name",
    "Access-Control-Max-Age": "600",
}


class _Handler(BaseHTTPRequestHandler):
    server_version = "BTP/0.1"

    def _route(self, method):
        body = None
        length = self.headers.get("Content-Length")
        if length:
            body = self.rfile.read(int(length))
        try:
            status, headers, response_body = bridge.dispatch_to_main(
                api.handle, method, self.path, body, dict(self.headers)
            )
        except Exception as e:
            payload = {"error": {"code": "internal_error", "message": str(e)}}
            self._write(500, {"Content-Type": "application/json; charset=utf-8"},
                        json.dumps(payload).encode("utf-8"))
            return
        self._write(status, headers, response_body)

    def _write(self, status, headers, body):
        self.send_response(status)
        body = body or b""
        for k, v in headers.items():
            self.send_header(k, v)
        for k, v in _CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        # CORS preflight：浏览器在发 PUT / POST 含自定义 header 前会先打这个
        self._write(204, {}, b"")

    def do_GET(self): self._route("GET")
    def do_PUT(self): self._route("PUT")
    def do_POST(self): self._route("POST")
    def do_DELETE(self): self._route("DELETE")

    def log_message(self, fmt, *args):
        pass


def start(port):
    global _server, _server_thread
    stop()
    _server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    _server_thread = threading.Thread(
        target=_server.serve_forever, daemon=True, name="BTP-HTTP")
    _server_thread.start()
    print(f"[BTP] localhost HTTP listening on 127.0.0.1:{port}")


def stop():
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server.server_close()
        _server = None
    if _server_thread is not None:
        _server_thread.join(timeout=2.0)
        _server_thread = None
