"""Mock KatanaMCP service for testing the MCP server without Katana.

Speaks the same JSON-lines protocol on 127.0.0.1:17820 and emulates a tiny
in-memory node graph, so you can develop / smoke-test the MCP side:

    python scripts/mock_katana.py
"""

import json
import socketserver
import threading

PORT = 17820

_nodes = {}          # path -> {"type": str}
_seq = 0
_log = []


def add_log(level, msg):
    global _seq
    _seq += 1
    _log.append({"seq": _seq, "time": "00:00:00", "timestamp": 0,
                 "level": level, "source": "mock", "message": msg})


def dispatch(method, params):
    global _seq
    if method == "get_info":
        return {"ok": True, "mock": True, "rootNodeChildren": len(_nodes)}
    if method == "exec":
        code = params.get("code", "")
        try:
            ns = {}
            exec(compile(code, "<mock>", "exec"), ns)
            return {"ok": True, "stdout": "", "stderr": "",
                    "result": ns.get("result"), "error": None}
        except Exception as e:
            add_log("ERROR", "Traceback: %s" % e)
            return {"ok": False, "stdout": "", "stderr": str(e),
                    "result": None,
                    "error": {"type": type(e).__name__, "message": str(e)}}
    if method == "create_node":
        name = params.get("name") or params["node_type"]
        _nodes[name] = {"type": params["node_type"]}
        add_log("INFO", "Created node %s" % name)
        return {"ok": True, "name": name, "path": name,
                "type": params["node_type"]}
    if method == "list_nodes":
        return {"ok": True, "parent": "/",
                "children": [{"name": n, "type": v["type"], "path": n}
                             for n, v in _nodes.items()]}
    if method == "delete_node":
        _nodes.pop(params["path"], None)
        return {"ok": True, "deleted": params["path"]}
    if method == "get_logs":
        since = params.get("since_seq", 0)
        entries = [e for e in _log if e["seq"] > since]
        return {"entries": entries[-params.get("max_lines", 200):],
                "currentSeq": _seq}
    if method == "log_seq":
        return {"currentSeq": _seq}
    if method == "clear_logs":
        _log[:] = []
        return {"cleared": True}
    if method == "ping":
        return {"ok": True, "service": "mock-katana-mcp"}
    raise ValueError("Unknown method: %s" % method)


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        while True:
            line = self.rfile.readline()
            if not line:
                return
            try:
                req = json.loads(line.decode("utf-8"))
                result = dispatch(req.get("method"), req.get("params") or {})
                resp = {"id": req.get("id"), "ok": True, "result": result}
            except Exception as e:
                resp = {"id": None, "ok": False,
                        "error": {"type": type(e).__name__,
                                  "message": str(e)}}
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


class Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    add_log("INFO", "Mock Katana MCP service started on port %d" % PORT)
    srv = Server(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("Mock Katana listening on 127.0.0.1:%d (Ctrl+C to stop)" % PORT)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
