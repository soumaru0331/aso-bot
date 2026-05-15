from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import os
import time
import urllib.request


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # ログ出力を抑制


def _self_ping(url: str) -> None:
    """4分おきに自分自身のURLにpingしてRenderのスリープを防ぐ。"""
    time.sleep(60)  # 起動直後は少し待つ
    while True:
        try:
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            pass
        time.sleep(240)  # 4分待機


def start_web_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"[KeepAlive] HTTP server running on port {port}")

    # 自己pingでスリープ防止（UptimeRobotが止まっても安全）
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if render_url:
        ping_thread = threading.Thread(target=_self_ping, args=(render_url,), daemon=True)
        ping_thread.start()
        print(f"[KeepAlive] Self-ping started → {render_url}")
