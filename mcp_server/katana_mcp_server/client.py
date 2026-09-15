"""Minimal JSON-lines TCP client for the in-Katana KatanaMCP service."""

import json
import socket
import threading

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 17820


class KatanaConnectionError(RuntimeError):
    """Raised when the Katana MCP service cannot be reached."""


class KatanaClient(object):
    """One socket per call, guarded by a lock. Simple and robust."""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=30.0):
        self.host = host
        self.port = int(port)
        self.timeout = timeout
        self._lock = threading.Lock()
        self._next_id = 0

    def call(self, method, **params):
        with self._lock:
            self._next_id += 1
            req_id = self._next_id
            request = json.dumps({"id": req_id, "method": method,
                                  "params": params}).encode("utf-8") + b"\n"
            try:
                sock = socket.create_connection((self.host, self.port),
                                                timeout=self.timeout)
            except OSError as e:
                raise KatanaConnectionError(
                    "Cannot connect to Katana MCP service at %s:%d - is "
                    "Katana running and the KatanaMCP service started? "
                    "(%s)" % (self.host, self.port, e))
            try:
                sock.settimeout(self.timeout)
                sock.sendall(request)
                buf = b""
                while b"\n" not in buf:
                    chunk = sock.recv(65536)
                    if not chunk:
                        raise KatanaConnectionError(
                            "Katana closed the connection unexpectedly")
                    buf += chunk
                line = buf.split(b"\n", 1)[0]
                response = json.loads(line.decode("utf-8"))
            finally:
                sock.close()

        if not response.get("ok"):
            err = response.get("error") or {}
            raise RuntimeError("Katana error (%s): %s"
                               % (err.get("type", "Error"),
                                  err.get("message", "unknown")))
        return response.get("result")
