"""Threaded JSON-lines TCP server running inside Katana.

Protocol: one UTF-8 JSON object per line, request and response.

Request:  {"id": 1, "method": "create_node", "params": {...}}
Response: {"id": 1, "ok": true, "result": {...}}
          {"id": 1, "ok": false, "error": {"type": ..., "message": ...}}

Special methods handled here (not in commands.py):
  get_logs, clear_logs, log_seq
"""

import json
import socket
import socketserver
import threading
import traceback

from . import commands, logcapture
from . import DEFAULT_PORT


class _RequestHandler(socketserver.StreamRequestHandler):
    def handle(self):
        buffer = self.server.log_buffer
        buffer.add("INFO", "katana-mcp",
                   "Client connected: %s" % (self.client_address[0],))
        while True:
            line = self.rfile.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line.decode("utf-8"))
            except ValueError:
                self._send({"id": None, "ok": False,
                            "error": {"type": "ProtocolError",
                                      "message": "Invalid JSON"}})
                continue
            response = self._dispatch(request, buffer)
            self._send(response)

    def _send(self, obj):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        self.wfile.write(data)

    def _dispatch(self, request, buffer):
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        try:
            if method == "get_logs":
                result = {"entries": buffer.get(
                    max_lines=params.get("max_lines", 200),
                    min_level=params.get("min_level"),
                    since_seq=params.get("since_seq", 0)),
                    "currentSeq": buffer.current_seq()}
            elif method == "clear_logs":
                buffer.clear()
                result = {"cleared": True}
            elif method == "log_seq":
                result = {"currentSeq": buffer.current_seq()}
            elif method in commands.COMMANDS:
                result = commands.COMMANDS[method](**params)
            else:
                raise ValueError("Unknown method: %r" % (method,))
            return {"id": req_id, "ok": True, "result": result}
        except Exception as e:
            return {"id": req_id, "ok": False,
                    "error": {"type": type(e).__name__,
                              "message": str(e),
                              "traceback": traceback.format_exc()}}


class _ThreadedTCPServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class KatanaMCPServer(object):
    """Lifecycle wrapper around the TCP server + log buffer."""

    def __init__(self):
        self.log_buffer = logcapture.LogBuffer(maxlen=5000)
        self._server = None
        self._thread = None
        self.port = None

    @property
    def running(self):
        return self._server is not None

    def start(self, port=DEFAULT_PORT):
        if self._server is not None:
            return False
        logcapture.install(self.log_buffer)
        server = _ThreadedTCPServer(("127.0.0.1", int(port)),
                                    _RequestHandler)
        server.log_buffer = self.log_buffer
        self._server = server
        self.port = int(port)
        self._thread = threading.Thread(
            target=server.serve_forever, name="KatanaMCPServer")
        self._thread.daemon = True
        self._thread.start()
        self.log_buffer.add("INFO", "katana-mcp",
                            "MCP service started on 127.0.0.1:%d" % self.port)
        return True

    def stop(self):
        if self._server is None:
            return False
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self.log_buffer.add("INFO", "katana-mcp", "MCP service stopped")
        return True

    def status(self):
        return {"running": self.running, "port": self.port}


_INSTANCE = None


def get_server():
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = KatanaMCPServer()
    return _INSTANCE
