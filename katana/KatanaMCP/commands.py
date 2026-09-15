"""Command implementations executed inside Katana's Python environment.

Every public ``cmd_*`` function takes plain JSON-serializable arguments and
returns a JSON-serializable dict. They are dispatched by server.py.
"""

import contextlib
import io
import json
import traceback


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _nodegraph():
    from Katana import NodegraphAPI
    return NodegraphAPI


def _resolve_node(path):
    """Resolve a node by path. Root-level nodes are addressed by name
    (e.g. ``"GafferThree"``); children of groups use slashes
    (e.g. ``"MyGroup/CameraCreate"``). ``None``/``""`` -> root node."""
    NodegraphAPI = _nodegraph()
    if not path or path in ("/", "."):
        return NodegraphAPI.GetRootNode()
    node = None
    for part in [p for p in path.strip("/").split("/") if p]:
        if node is None:
            node = NodegraphAPI.GetNode(part)
        else:
            node = node.getChild(part)
        if node is None:
            raise ValueError("Node not found: %r (failed at %r)" % (path, part))
    return node


def _node_path(node):
    parts = []
    NodegraphAPI = _nodegraph()
    root = NodegraphAPI.GetRootNode()
    while node is not None and node != root:
        parts.append(node.getName())
        node = node.getParent()
    return "/".join(reversed(parts))


def _parameter_to_dict(param, time=0):
    info = {
        "name": param.getName(),
        "fullName": param.getFullName(),
        "numChildren": param.getNumChildren(),
    }
    if param.getNumChildren() == 0:
        try:
            info["value"] = param.getValue(time)
        except Exception as e:
            info["value"] = "<unreadable: %s>" % e
    return info


def _serialize_exception(exc):
    return {"type": type(exc).__name__, "message": str(exc),
            "traceback": traceback.format_exc()}


# ---------------------------------------------------------------------------
# ping / info
# ---------------------------------------------------------------------------

def cmd_get_info():
    from Katana import KatanaFile
    info = {"ok": True}
    try:
        import os
        info["project"] = os.environ.get("KATANA_PROJECT_FILE")
    except Exception:
        pass
    try:
        NodegraphAPI = _nodegraph()
        root = NodegraphAPI.GetRootNode()
        info["rootNodeChildren"] = len(root.getChildren())
    except Exception:
        pass
    try:
        from Katana import Configuration
        info["katanaVersion"] = Configuration.get("KATANA_RELEASE") or None
    except Exception:
        pass
    try:
        info["projectFile"] = KatanaFile.GetFileName()
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# python execution
# ---------------------------------------------------------------------------

def cmd_exec(code, time_budget=None):
    """Execute arbitrary Python inside Katana. ``result`` may be assigned by
    the executed code to return a JSON-serializable value."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = {}
    try:
        from Katana import NodegraphAPI, UI4, Utils  # noqa: F401
        namespace.update({
            "NodegraphAPI": NodegraphAPI,
            "UI4": UI4,
            "Utils": Utils,
        })
    except Exception:
        pass
    error = None
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exec(compile(code, "<katana-mcp>", "exec"), namespace)
        except Exception as e:
            error = _serialize_exception(e)
    result = namespace.get("result")
    try:
        json.dumps(result)
    except (TypeError, ValueError):
        result = repr(result)
    return {
        "ok": error is None,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
        "result": result,
        "error": error,
    }


def cmd_eval(expression):
    stdout = io.StringIO()
    namespace = {}
    try:
        from Katana import NodegraphAPI, UI4, Utils  # noqa: F401
        namespace.update({"NodegraphAPI": NodegraphAPI, "UI4": UI4,
                          "Utils": Utils})
    except Exception:
        pass
    error = None
    value = None
    with contextlib.redirect_stdout(stdout):
        try:
            value = eval(compile(expression, "<katana-mcp>", "eval"),
                         namespace)
        except Exception as e:
            error = _serialize_exception(e)
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        value = repr(value)
    return {"ok": error is None, "stdout": stdout.getvalue(),
            "value": value, "error": error}


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------

def cmd_create_node(node_type, name=None, parent=None):
    NodegraphAPI = _nodegraph()
    parent_node = _resolve_node(parent)
    node = NodegraphAPI.CreateNode(node_type, parent_node)
    if name:
        node.setName(name)
    return {"ok": True, "name": node.getName(), "path": _node_path(node),
            "type": node.getType()}


def cmd_delete_node(path):
    node = _resolve_node(path)
    name = node.getName()
    node.delete()
    return {"ok": True, "deleted": name}


def cmd_rename_node(path, new_name):
    node = _resolve_node(path)
    node.setName(new_name)
    return {"ok": True, "path": _node_path(node)}


def cmd_list_nodes(parent=None):
    parent_node = _resolve_node(parent)
    children = []
    try:
        it = parent_node.getChildren()
    except Exception:
        it = []
    for child in it:
        children.append({
            "name": child.getName(),
            "type": child.getType(),
            "path": _node_path(child),
        })
    return {"ok": True, "parent": parent or "/", "children": children}


def cmd_get_node_info(path):
    node = _resolve_node(path)
    params = []
    try:
        for child in node.getParameters().getChildren():
            params.append(_parameter_to_dict(child))
    except Exception:
        pass
    inputs = [p.getName() for p in node.getInputPorts()]
    outputs = [p.getName() for p in node.getOutputPorts()]
    return {
        "ok": True,
        "name": node.getName(),
        "type": node.getType(),
        "path": _node_path(node),
        "inputPorts": inputs,
        "outputPorts": outputs,
        "parameters": params,
    }


def cmd_get_node_types(filter=None):
    NodegraphAPI = _nodegraph()
    types = None
    for fn_name in ("GetNodeTypes", "GetAllRegisteredNodeTypes"):
        fn = getattr(NodegraphAPI, fn_name, None)
        if fn:
            try:
                types = list(fn())
                break
            except Exception:
                pass
    if types is None:
        return {"ok": False,
                "error": "Could not enumerate node types on this Katana "
                         "version"}
    if filter:
        f = filter.lower()
        types = [t for t in types if f in t.lower()]
    types = sorted(types)
    return {"ok": True, "count": len(types), "types": types[:2000]}


# ---------------------------------------------------------------------------
# parameters
# ---------------------------------------------------------------------------

def cmd_set_parameter(node_path, parameter, value, time=0):
    node = _resolve_node(node_path)
    param = node.getParameter(parameter)
    if param is None:
        raise ValueError("Parameter %r not found on node %r"
                         % (parameter, node_path))
    param.setValue(value, time)
    return {"ok": True, "node": node_path, "parameter": parameter,
            "value": param.getValue(time)}


def cmd_get_parameter(node_path, parameter, time=0):
    node = _resolve_node(node_path)
    param = node.getParameter(parameter)
    if param is None:
        raise ValueError("Parameter %r not found on node %r"
                         % (parameter, node_path))
    return {"ok": True, **_parameter_to_dict(param, time)}


# ---------------------------------------------------------------------------
# connections
# ---------------------------------------------------------------------------

def cmd_connect(source, target, source_port=None, target_port=None):
    src = _resolve_node(source)
    dst = _resolve_node(target)
    out_ports = src.getOutputPorts()
    in_ports = dst.getInputPorts()
    if not out_ports:
        raise ValueError("Source node %r has no output ports" % source)
    if not in_ports:
        raise ValueError("Target node %r has no input ports" % target)
    out_port = (src.getOutputPort(source_port) if source_port
                else out_ports[0])
    in_port = (dst.getInputPort(target_port) if target_port
               else in_ports[0])
    if out_port is None:
        raise ValueError("Output port %r not found on %r"
                         % (source_port, source))
    if in_port is None:
        raise ValueError("Input port %r not found on %r"
                         % (target_port, target))
    out_port.connect(in_port)
    return {"ok": True, "source": source, "target": target,
            "sourcePort": out_port.getName(),
            "targetPort": in_port.getName()}


def cmd_disconnect(source, target):
    src = _resolve_node(source)
    dst = _resolve_node(target)
    removed = 0
    for out_port in src.getOutputPorts():
        for in_port in list(out_port.getConnectedPorts()):
            if in_port.getNode() == dst:
                out_port.disconnect(in_port)
                removed += 1
    return {"ok": True, "disconnected": removed}


# ---------------------------------------------------------------------------
# project file
# ---------------------------------------------------------------------------

def cmd_save_project(path=None):
    from Katana import KatanaFile
    if path:
        KatanaFile.Save(path)
        return {"ok": True, "saved": path}
    current = KatanaFile.GetFileName()
    if not current:
        raise ValueError("No file path given and the current project has "
                         "never been saved.")
    KatanaFile.Save(current)
    return {"ok": True, "saved": current}


# ---------------------------------------------------------------------------
# dispatch table
# ---------------------------------------------------------------------------

COMMANDS = {
    "ping": lambda: {"ok": True, "service": "katana-mcp"},
    "get_info": cmd_get_info,
    "exec": cmd_exec,
    "eval": cmd_eval,
    "create_node": cmd_create_node,
    "delete_node": cmd_delete_node,
    "rename_node": cmd_rename_node,
    "list_nodes": cmd_list_nodes,
    "get_node_info": cmd_get_node_info,
    "get_node_types": cmd_get_node_types,
    "set_parameter": cmd_set_parameter,
    "get_parameter": cmd_get_parameter,
    "connect": cmd_connect,
    "disconnect": cmd_disconnect,
    "save_project": cmd_save_project,
}
