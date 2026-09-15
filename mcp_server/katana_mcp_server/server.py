"""FastMCP server exposing Foundry Katana as MCP tools.

Run over stdio (standard for MCP clients):

    katana-mcp                    # entry point installed by the package
    python -m katana_mcp_server   # equivalent

Connection to Katana is configured via env vars:
    KATANA_MCP_HOST  (default 127.0.0.1)
    KATANA_MCP_PORT  (default 17820)
"""

import json
import os
import re

from mcp.server.fastmcp import FastMCP

from .client import DEFAULT_HOST, DEFAULT_PORT, KatanaClient

mcp = FastMCP("katana-mcp")

_client = KatanaClient(
    host=os.environ.get("KATANA_MCP_HOST", DEFAULT_HOST),
    port=int(os.environ.get("KATANA_MCP_PORT", DEFAULT_PORT)),
)


def _fmt_error(e):
    return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# connection / status
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_status() -> dict:
    """Check whether the Katana MCP service is reachable and get basic
    info about the running Katana instance (project file, node count)."""
    try:
        return {"ok": True, "katana": _client.call("get_info")}
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_get_logs(max_lines: int = 200, min_level: str = None) -> dict:
    """Read captured Katana log output (application messages, script output,
    render logs printed to the console).

    Args:
        max_lines: Maximum number of most-recent entries to return.
        min_level: Optional filter: DEBUG, INFO, WARNING or ERROR.
    """
    try:
        params = {"max_lines": max_lines}
        if min_level:
            params["min_level"] = min_level
        return _client.call("get_logs", **params)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_clear_logs() -> dict:
    """Clear the captured log buffer inside Katana."""
    try:
        return _client.call("clear_logs")
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# script execution
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_execute_python(code: str) -> dict:
    """Execute arbitrary Python inside Katana's interpreter. The Katana
    modules NodegraphAPI, UI4 and Utils are pre-imported into the namespace.
    Assign a JSON-serializable value to the variable ``result`` to return it.

    Returns stdout, stderr, result and any exception traceback.
    """
    try:
        return _client.call("exec", code=code)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_eval(expression: str) -> dict:
    """Evaluate a single Python expression inside Katana and return its
    value (NodegraphAPI / UI4 / Utils pre-imported)."""
    try:
        return _client.call("eval", expression=expression)
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_create_node(node_type: str, name: str = None,
                       parent: str = None) -> dict:
    """Create a node in the Katana node graph.

    Args:
        node_type: e.g. "GafferThree", "CameraCreate", "RenderSettings",
            "Material", "PrmanShadingNode", "Merge".
        name: Optional name for the new node.
        parent: Optional path of a group node to create inside
            (e.g. "MyGroup"). Defaults to the root of the node graph.

    Returns the created node's name and full path.
    """
    try:
        params = {"node_type": node_type}
        if name:
            params["name"] = name
        if parent:
            params["parent"] = parent
        return _client.call("create_node", **params)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_delete_node(path: str) -> dict:
    """Delete a node by path (e.g. "GafferThree" or "MyGroup/CameraCreate")."""
    try:
        return _client.call("delete_node", path=path)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_rename_node(path: str, new_name: str) -> dict:
    """Rename a node."""
    try:
        return _client.call("rename_node", path=path, new_name=new_name)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_list_nodes(parent: str = None) -> dict:
    """List child nodes of the root node graph (or of a given group node
    path). Returns name, type and path for each child."""
    try:
        params = {}
        if parent:
            params["parent"] = parent
        return _client.call("list_nodes", **params)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_get_node_info(path: str) -> dict:
    """Get details for a node: type, input/output ports and top-level
    parameters with current values."""
    try:
        return _client.call("get_node_info", path=path)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_get_node_types(filter: str = None) -> dict:
    """List node types that can be created in this Katana session.
    Use the optional substring filter (e.g. "gaffer", "camera", "render")
    to keep the list manageable."""
    try:
        params = {}
        if filter:
            params["filter"] = filter
        return _client.call("get_node_types", **params)
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_set_parameter(node_path: str, parameter: str, value,
                         time: float = 0) -> dict:
    """Set a parameter value on a node.

    Args:
        node_path: Node path, e.g. "RenderSettings" or "MyGroup/Camera".
        parameter: Parameter name; nested parameters use dot notation,
            e.g. "resolution.x", "cropWindow", "shutter.close".
        value: New value (number, string, bool or list as appropriate).
        time: Frame time for the value (default 0).
    """
    try:
        return _client.call("set_parameter", node_path=node_path,
                            parameter=parameter, value=value, time=time)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_get_parameter(node_path: str, parameter: str,
                         time: float = 0) -> dict:
    """Read a parameter value from a node. Nested parameters use dot
    notation, e.g. "resolution.y"."""
    try:
        return _client.call("get_parameter", node_path=node_path,
                            parameter=parameter, time=time)
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# connections
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_connect_nodes(source: str, target: str,
                         source_port: str = None,
                         target_port: str = None) -> dict:
    """Connect two nodes. By default the first output port of ``source`` is
    connected to the first input port of ``target``; port names can be given
    explicitly for multi-port nodes (see katana_get_node_info)."""
    try:
        params = {"source": source, "target": target}
        if source_port:
            params["source_port"] = source_port
        if target_port:
            params["target_port"] = target_port
        return _client.call("connect", **params)
    except Exception as e:
        return _fmt_error(e)


@mcp.tool()
def katana_disconnect_nodes(source: str, target: str) -> dict:
    """Remove all connections between two nodes."""
    try:
        return _client.call("disconnect", source=source, target=target)
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_save_project(path: str = None) -> dict:
    """Save the current Katana project. If no path is given, saves to the
    current project file (fails if the project was never saved)."""
    try:
        params = {}
        if path:
            params["path"] = path
        return _client.call("save_project", **params)
    except Exception as e:
        return _fmt_error(e)


# ---------------------------------------------------------------------------
# verification
# ---------------------------------------------------------------------------

@mcp.tool()
def katana_verify(code: str = None, error_pattern: str = None,
                  max_log_lines: int = 100) -> dict:
    """Run an action and verify the result against the Katana log.

    Records the current log position, optionally executes ``code`` in
    Katana, then scans every log entry produced since for errors. A log
    entry counts as an error when its level is ERROR/CRITICAL/STDERR or
    its message matches common failure signatures (Traceback, "error",
    "failed", "exception") - or the optional custom ``error_pattern``
    regex.

    Returns:
        success: True when no error-like log entries were captured.
        matchedErrors: the offending log entries (if any).
        exec: the execution result (when ``code`` was given).
    """
    try:
        start = _client.call("log_seq")["currentSeq"]
        exec_result = None
        if code:
            exec_result = _client.call("exec", code=code)
        logs = _client.call("get_logs", max_lines=max_log_lines,
                            since_seq=start)
        custom = re.compile(error_pattern, re.IGNORECASE) \
            if error_pattern else None
        default = re.compile(
            r"traceback|\berror\b|\bfailed\b|exception|critical",
            re.IGNORECASE)
        bad = []
        for e in logs.get("entries", []):
            is_bad = e["level"] in ("ERROR", "CRITICAL", "STDERR") \
                or default.search(e["message"]) is not None
            if custom and custom.search(e["message"]):
                is_bad = True
            if is_bad:
                bad.append(e)
        out = {
            "success": len(bad) == 0 and (
                exec_result is None or exec_result.get("ok", False)),
            "matchedErrors": bad,
            "logEntriesScanned": len(logs.get("entries", [])),
        }
        if exec_result is not None:
            out["exec"] = exec_result
        return out
    except Exception as e:
        return _fmt_error(e)


def main():
    host = os.environ.get("KATANA_MCP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("KATANA_MCP_PORT", DEFAULT_PORT))
    _client.host = host
    _client.port = port
    mcp.run()


if __name__ == "__main__":
    main()
