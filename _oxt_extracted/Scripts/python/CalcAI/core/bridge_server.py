"""HTTP Bridge Server - LO Python'da çalışır, stdlib-only.

LibreOffice'un gömülü Python'unda çalışarak sistem Python (PyQt5) ile
JSON-over-HTTP iletişim sağlar. UNO context üzerinden hücre okuma/yazma
gibi işlemleri HTTP endpoint'leri olarak sunar.
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logger = logging.getLogger("CalcAI.bridge_server")


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the bridge server."""

    def log_message(self, format, *args):
        """Redirect http.server logs to our logger."""
        logger.debug(format, *args)

    def _send_json(self, data, status=200):
        """Send a JSON response."""
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/ping":
            self._send_json({"status": "ok"})
        elif self.path == "/context":
            self._handle_context()
        else:
            self._send_json({"error": f"Unknown endpoint: {self.path}"}, 404)

    def do_POST(self):
        if self.path == "/dispatch":
            self._handle_dispatch()
        else:
            self._send_json({"error": f"Unknown endpoint: {self.path}"}, 404)

    def _read_body(self) -> dict:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def _handle_dispatch(self):
        """Handle POST /dispatch - execute a tool via ToolDispatcher."""
        try:
            body = self._read_body()
            tool_name = body.get("tool")
            args = body.get("args", {})

            if not tool_name:
                self._send_json({"error": "Missing 'tool' field"}, 400)
                return

            dispatcher = self.server.dispatcher
            if dispatcher is None:
                self._send_json({"error": "Dispatcher not initialized"}, 503)
                return

            result_str = dispatcher.dispatch(tool_name, args)
            # dispatch returns JSON string, parse and re-send
            try:
                result = json.loads(result_str)
            except (json.JSONDecodeError, TypeError):
                result = {"result": result_str}

            self._send_json(result)

        except Exception as e:
            logger.error("Dispatch error: %s", e, exc_info=True)
            self._send_json({"error": str(e)}, 500)

    def _handle_context(self):
        """Handle GET /context - return sheet summary + selection info."""
        try:
            context_func = self.server.context_func
            if context_func is None:
                self._send_json({"error": "Context function not set"}, 503)
                return

            context_data = context_func()
            self._send_json(context_data)

        except Exception as e:
            logger.error("Context error: %s", e, exc_info=True)
            self._send_json({"error": str(e)}, 500)


class BridgeServer:
    """HTTP bridge server that runs in a background thread.

    Usage:
        server = BridgeServer(dispatcher, context_func)
        port = server.start()  # returns assigned port
        # ... later ...
        server.stop()
    """

    def __init__(self, dispatcher=None, context_func=None):
        """Initialize bridge server.

        Args:
            dispatcher: ToolDispatcher instance for handling /dispatch calls.
            context_func: Callable returning dict for /context endpoint.
        """
        self._dispatcher = dispatcher
        self._context_func = context_func
        self._httpd = None
        self._thread = None
        self._port = 0

    @property
    def port(self) -> int:
        return self._port

    def start(self) -> int:
        """Start the server on a random available port. Returns the port number."""
        self._httpd = HTTPServer(("127.0.0.1", 0), BridgeRequestHandler)
        self._httpd.dispatcher = self._dispatcher
        self._httpd.context_func = self._context_func
        self._port = self._httpd.server_address[1]

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="BridgeServer",
        )
        self._thread.start()

        logger.info("Bridge server started on port %d", self._port)
        return self._port

    def stop(self):
        """Shut down the server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("Bridge server stopped")

    def set_dispatcher(self, dispatcher):
        """Update the dispatcher (e.g. after UNO context is ready)."""
        self._dispatcher = dispatcher
        if self._httpd:
            self._httpd.dispatcher = dispatcher

    def set_context_func(self, context_func):
        """Update the context function."""
        self._context_func = context_func
        if self._httpd:
            self._httpd.context_func = context_func
