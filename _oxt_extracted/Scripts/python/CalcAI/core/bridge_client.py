"""HTTP Bridge Client - Sistem Python'da çalışır.

BridgeServer'a HTTP üzerinden bağlanarak LibreOffice UNO işlemlerini
uzaktan çağırır. ToolDispatcher ile aynı dispatch(tool_name, args) arayüzünü sunar.
"""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("CalcAI.bridge_client")


class BridgeClient:
    """HTTP client for communicating with BridgeServer running in LO Python.

    Provides the same dispatch(tool_name, args) -> str interface as ToolDispatcher,
    so MainWindow can use it transparently.

    Usage:
        client = BridgeClient(port=12345)
        if client.is_connected:
            result = client.dispatch("read_cell_range", {"range_name": "A1:B5"})
    """

    def __init__(self, port: int, host: str = "127.0.0.1", timeout: int = 10):
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout

    @property
    def is_connected(self) -> bool:
        """Check if the bridge server is reachable."""
        try:
            req = urllib.request.Request(f"{self._base_url}/ping")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok"
        except Exception:
            return False

    def dispatch(self, tool_name: str, arguments: dict) -> str:
        """Execute a tool via the bridge server.

        Args:
            tool_name: Tool name (e.g. "read_cell_range").
            arguments: Tool arguments dict.

        Returns:
            JSON string with the result (same format as ToolDispatcher.dispatch).
        """
        try:
            payload = json.dumps({
                "tool": tool_name,
                "args": arguments,
            }).encode("utf-8")

            req = urllib.request.Request(
                f"{self._base_url}/dispatch",
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                result = resp.read().decode("utf-8")
                return result

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            logger.error("Bridge dispatch HTTP error %d: %s", e.code, error_body)
            return json.dumps({"error": f"Bridge HTTP error {e.code}: {error_body}"})
        except Exception as e:
            logger.error("Bridge dispatch error: %s", e)
            return json.dumps({"error": f"Bridge connection error: {e}"})

    def get_context(self) -> dict:
        """Get sheet context (summary + selection) from the bridge server.

        Returns:
            Dict with sheet context info, or error dict.
        """
        try:
            req = urllib.request.Request(f"{self._base_url}/context")
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data
        except Exception as e:
            logger.error("Bridge context error: %s", e)
            return {"error": str(e)}
