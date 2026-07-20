from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import threading
import time

class StatusServer:
    """
    HTTP server to be run on a daemon thread. Provides a read-only view of current state

    GET /health -> 200 {"status" : "ok", "uptime_seconds": ...}
    GET /status -> 200 JSON: per-product last status, last check time, last latency, error counts since startup
    """

    def __init__(self, port: int, get_snapshot):
        start_time = time.monotonic()
        
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    body = {"status": "ok", "uptime_seconds": time.monotonic() - start_time}
                    self._respond(200, body)
                elif self.path == "/status":
                    body = get_snapshot()
                    self._respond(200, body)
                else:
                    # Send a 404
                    body = {"error": "not found"}
                    self._respond(404, body)
            
            def _respond(self, code, body):
                payload = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(payload)

        
        self.server = ThreadingHTTPServer(("", port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
    
    def start(self):
        self.thread.start()


if __name__ == "__main__":
    s = StatusServer(8080, lambda: {"products": {"fake": {"last_status": "IN_STOCK"}}})
    s.start()
    while True:
        time.sleep(1)