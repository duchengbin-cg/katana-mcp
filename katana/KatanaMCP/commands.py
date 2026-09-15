"""Command implementations executed inside Katana's Python environment.

Every public ``cmd_*`` function takes plain JSON-serializable arguments and
returns a JSON-serializable dict. They are dispatched by server.py.

Note on robustness: Katana's Python API varies a little between releases, so
version-sensitive calls are wrapped in guards and report honestly instead of
crashing the service.
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


def _copy_param_values(src, dst, time=0):
    """Recursively copy leaf parameter values from src group to dst group."""
    for child in src.getChildren():
        try:
            target = dst.getChild(child.getName())
        except Exception:
            target = None
        if target is None:
            continue
        if child.getNumChildren() == 0:
            try:
                target.setValue(child.getValue(time), time)
            except Exception:
                pass
        else:
            _copy_param_values(child, target, time)


def _walk_nodes(parent):
    """Yield (path, node) for parent and all descendants."""
    yield _node_path(parent), parent
    try:
        children = parent.getChildren()
    except Exception:
        return
    for child in children:
        for item in _walk_nodes(child):
            yield item


def _get_position(node):
    NodegraphAPI = _nodegraph()
    try:
        x, y = NodegraphAPI.GetNodePosition(node)
        return [x, y]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ping / info
# ---------------------------------------------------------------------------

def cmd_get_info():
    info = {"ok": True, "service": "katana-mcp"}
    try:
        NodegraphAPI = _nodegraph()
        root = NodegraphAPI.GetRootNode()
        info["rootNodeChildren"] = len(root.getChildren())
    except Exception:
        pass
    try:
        from Katana import Configuration
        info["katanaVersion"] = (Configuration.get("KATANA_RELEASE")
                                 or Configuration.get("KATANA_VERSION"))
    except Exception:
        pass
    try:
        from Katana import KatanaFile
        info["projectFile"] = KatanaFile.GetFileName()
    except Exception:
        pass
    try:
        import os
        info["pid"] = os.getpid()
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# python execution
# ---------------------------------------------------------------------------

def _exec_namespace():
    namespace = {}
    try:
        from Katana import NodegraphAPI, UI4, Utils, KatanaFile  # noqa: F401
        namespace.update({
            "NodegraphAPI": NodegraphAPI,
            "UI4": UI4,
            "Utils": Utils,
            "KatanaFile": KatanaFile,
        })
    except Exception:
        pass
    return namespace


def cmd_exec(code, time_budget=None):
    """Execute arbitrary Python inside Katana. ``result`` may be assigned by
    the executed code to return a JSON-serializable value."""
    stdout = io.StringIO()
    stderr = io.StringIO()
    namespace = _exec_namespace()
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
    namespace = _exec_namespace()
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
    return {"ok": True, "stdout": stdout.getvalue(),
            "value": value, "error": error}


# ---------------------------------------------------------------------------
# nodes: lifecycle
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


def cmd_duplicate_node(path, name=None):
    NodegraphAPI = _nodegraph()
    node = _resolve_node(path)
    parent = node.getParent()
    new_node = NodegraphAPI.CreateNode(node.getType(), parent)

    # Prefer full parameter XML round-trip; fall back to value copying.
    param_mode = "values"
    try:
        xml = node.getParameters().getXml()
        new_node.getParameters().replaceWithXml(xml)
        param_mode = "xml"
    except Exception:
        _copy_param_values(node.getParameters(), new_node.getParameters())

    if name:
        new_node.setName(name)

    # Copy incoming connections port-by-port.
    copied_connections = 0
    for in_port in node.getInputPorts():
        try:
            targets = list(in_port.getConnectedPorts())
        except Exception:
            targets = []
        for src_port in targets:
            try:
                dst = new_node.getInputPort(in_port.getName())
                if dst is not None:
                    src_port.connect(dst)
                    copied_connections += 1
            except Exception:
                pass

    pos = _get_position(node)
    if pos:
        try:
            NodegraphAPI.SetNodePosition(new_node,
                                         (pos[0] + 120, pos[1] + 120))
        except Exception:
            pass

    return {"ok": True, "path": _node_path(new_node),
            "parameterMode": param_mode,
            "copiedConnections": copied_connections}


def cmd_list_nodes(parent=None, recursive=False, max_nodes=2000):
    parent_node = _resolve_node(parent)
    children = []

    def add(node, depth):
        if len(children) >= max_nodes:
            return
        children.append({
            "name": node.getName(),
            "type": node.getType(),
            "path": _node_path(node),
            "depth": depth,
        })
        if recursive:
            try:
                for c in node.getChildren():
                    add(c, depth + 1)
            except Exception:
                pass

    try:
        for child in parent_node.getChildren():
            add(child, 0)
    except Exception:
        pass
    return {"ok": True, "parent": parent or "/", "count": len(children),
            "children": children}


def cmd_get_node_tree(parent=None, max_depth=4):
    parent_node = _resolve_node(parent)

    def build(node, depth):
        entry = {"name": node.getName(), "type": node.getType(),
                 "path": _node_path(node)}
        if depth < max_depth:
            try:
                kids = [build(c, depth + 1) for c in node.getChildren()]
                if kids:
                    entry["children"] = kids
            except Exception:
                pass
        return entry

    tree = {"name": "/", "type": "Root", "path": "",
            "children": [build(c, 0)
                         for c in parent_node.getChildren()]}
    return {"ok": True, "tree": tree}


def cmd_find_nodes(name_contains=None, node_type=None, parent=None,
                   max_results=500):
    parent_node = _resolve_node(parent)
    matches = []
    needle = name_contains.lower() if name_contains else None
    for path, node in _walk_nodes(parent_node):
        if path == "":
            continue  # skip root itself
        if needle and needle not in node.getName().lower():
            continue
        if node_type and node.getType() != node_type:
            continue
        matches.append({"name": node.getName(), "type": node.getType(),
                        "path": path})
        if len(matches) >= max_results:
            break
    return {"ok": True, "count": len(matches), "matches": matches}


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
        "position": _get_position(node),
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
# nodes: selection & layout
# ---------------------------------------------------------------------------

def cmd_select_nodes(paths, exclusive=True):
    NodegraphAPI = _nodegraph()
    nodes = [_resolve_node(p) for p in paths]
    if exclusive:
        NodegraphAPI.SetAllSelectedNodes(nodes)
    else:
        current = list(NodegraphAPI.GetAllSelectedNodes())
        NodegraphAPI.SetAllSelectedNodes(current + nodes)
    return {"ok": True, "selected": [_node_path(n) for n in nodes]}


def cmd_get_selected_nodes():
    NodegraphAPI = _nodegraph()
    nodes = NodegraphAPI.GetAllSelectedNodes()
    return {"ok": True,
            "selected": [{"name": n.getName(), "type": n.getType(),
                          "path": _node_path(n)} for n in nodes]}


def cmd_set_node_position(path, x, y):
    NodegraphAPI = _nodegraph()
    node = _resolve_node(path)
    NodegraphAPI.SetNodePosition(node, (float(x), float(y)))
    return {"ok": True, "path": path, "position": [float(x), float(y)]}


def cmd_get_node_position(path):
    node = _resolve_node(path)
    pos = _get_position(node)
    if pos is None:
        raise ValueError("Position unavailable for %r" % path)
    return {"ok": True, "path": path, "position": pos}


def cmd_arrange_nodes(paths=None, parent=None, x_spacing=260, y_spacing=120,
                      origin_x=0, origin_y=0, direction="horizontal"):
    """Simple layered auto-layout: columns (or rows) by connection depth.

    Nodes with no inputs inside the set start at depth 0; everything else is
    placed one layer past its deepest upstream dependency.
    """
    NodegraphAPI = _nodegraph()
    if paths:
        nodes = [_resolve_node(p) for p in paths]
    else:
        selected = list(NodegraphAPI.GetAllSelectedNodes())
        if selected:
            nodes = selected
        else:
            nodes = list(_resolve_node(parent).getChildren())
    if not nodes:
        return {"ok": True, "arranged": 0}

    node_set = set(nodes)
    depth_cache = {}

    def depth_of(node, visiting):
        if node in depth_cache:
            return depth_cache[node]
        if node in visiting:
            return 0
        visiting.add(node)
        d = 0
        for in_port in node.getInputPorts():
            try:
                srcs = list(in_port.getConnectedPorts())
            except Exception:
                srcs = []
            for src in srcs:
                src_node = src.getNode()
                if src_node in node_set:
                    d = max(d, depth_of(src_node, visiting) + 1)
        visiting.discard(node)
        depth_cache[node] = d
        return d

    layers = {}
    for node in nodes:
        layers.setdefault(depth_of(node, set()), []).append(node)

    arranged = 0
    for depth in sorted(layers):
        column = sorted(layers[depth], key=lambda n: n.getName())
        for index, node in enumerate(column):
            if direction == "horizontal":
                pos = (origin_x + depth * x_spacing,
                       origin_y + index * y_spacing)
            else:
                pos = (origin_x + index * x_spacing,
                       origin_y + depth * y_spacing)
            try:
                NodegraphAPI.SetNodePosition(node, pos)
                arranged += 1
            except Exception:
                pass
    return {"ok": True, "arranged": arranged, "layers": len(layers)}


# ---------------------------------------------------------------------------
# nodes: backdrop & notes
# ---------------------------------------------------------------------------

def cmd_create_backdrop(text="", x=0, y=0, width=None, height=None,
                        name=None, parent=None):
    NodegraphAPI = _nodegraph()
    parent_node = _resolve_node(parent)
    node = NodegraphAPI.CreateNode("Backdrop", parent_node)
    applied = {"position": False, "text": False, "size": False}

    try:
        NodegraphAPI.SetNodePosition(node, (float(x), float(y)))
        applied["position"] = True
    except Exception:
        pass

    if name:
        try:
            node.setName(name)
        except Exception:
            pass

    if text:
        param = node.getParameter("text")
        if param is not None:
            try:
                param.setValue(text, 0)
                applied["text"] = True
            except Exception:
                pass

    if width is not None and height is not None:
        # Backdrop extents are stored as node shape attributes; the exact
        # accessor differs between Katana versions, so try the known options.
        for fn_name in ("SetNodeShapeAttributes", "SetNodeShapeAttrs"):
            fn = getattr(NodegraphAPI, fn_name, None)
            if not fn:
                continue
            try:
                fn(node, {"width": float(width), "height": float(height)})
                applied["size"] = True
                break
            except Exception:
                continue
        if not applied["size"]:
            try:
                node.setShapeAttributes({"width": float(width),
                                         "height": float(height)})
                applied["size"] = True
            except Exception:
                pass

    note = None
    if width is not None and not applied["size"]:
        note = ("Size could not be applied on this Katana version; "
                "resize manually in the node graph.")
    return {"ok": True, "path": _node_path(node), "applied": applied,
            "note": note}


_NOTE_PARAM = "mcpNote"


def cmd_set_node_note(path, note):
    node = _resolve_node(path)
    params = node.getParameters()
    param = node.getParameter(_NOTE_PARAM)
    if param is None:
        param = params.createChildString(_NOTE_PARAM, "")
    param.setValue(note, 0)
    return {"ok": True, "path": path}


def cmd_get_node_note(path):
    node = _resolve_node(path)
    param = node.getParameter(_NOTE_PARAM)
    if param is None:
        return {"ok": True, "path": path, "note": None}
    return {"ok": True, "path": path, "note": param.getValue(0)}


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
# project file & project settings
# ---------------------------------------------------------------------------

def cmd_new_project():
    from Katana import KatanaFile
    for fn_name in ("New", "NewFile", "CreateNew"):
        fn = getattr(KatanaFile, fn_name, None)
        if fn:
            fn()
            return {"ok": True, "method": fn_name}
    raise RuntimeError(
        "No programmatic 'new project' entry point found on this Katana "
        "version. Use open_project with a .katana template file instead.")


def cmd_open_project(path):
    from Katana import KatanaFile
    KatanaFile.Load(path)
    return {"ok": True, "opened": path,
            "warning": "Any unsaved changes in the previous project were "
                       "discarded."}


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


def cmd_get_project_settings():
    """Project Settings parameters live on the root node; expose them all."""
    NodegraphAPI = _nodegraph()
    root = NodegraphAPI.GetRootNode()
    settings = {}
    for child in root.getParameters().getChildren():
        settings[child.getName()] = _parameter_to_dict(child)
    return {"ok": True, "count": len(settings), "settings": settings}


def cmd_set_project_setting(name, value, time=0):
    NodegraphAPI = _nodegraph()
    root = NodegraphAPI.GetRootNode()
    param = root.getParameter(name)
    if param is None:
        available = [c.getName() for c in root.getParameters().getChildren()]
        raise ValueError("Project setting %r not found. Available: %s"
                         % (name, ", ".join(available[:50])))
    param.setValue(value, time)
    return {"ok": True, "setting": name, "value": param.getValue(time)}


# ---------------------------------------------------------------------------
# graph state variables
# ---------------------------------------------------------------------------

def _gsv_group():
    NodegraphAPI = _nodegraph()
    root = NodegraphAPI.GetRootNode()
    return root.getParameter("variables")


def cmd_get_gsv():
    group = _gsv_group()
    variables = {}
    if group is not None:
        for child in group.getChildren():
            try:
                name_p = child.getChild("name")
                value_p = child.getChild("value")
                if name_p is None:
                    continue
                entry = {"value": value_p.getValue(0)
                         if value_p is not None else None}
                enabled_p = child.getChild("enabled")
                if enabled_p is not None:
                    entry["enabled"] = bool(enabled_p.getValue(0))
                variables[name_p.getValue(0)] = entry
            except Exception:
                pass
    return {"ok": True, "count": len(variables), "variables": variables}


def cmd_set_gsv(name, value, enabled=True):
    group = _gsv_group()
    if group is None:
        raise RuntimeError("No GSV parameter group ('variables') found on "
                           "the root node.")
    target = None
    for child in group.getChildren():
        try:
            name_p = child.getChild("name")
            if name_p is not None and name_p.getValue(0) == name:
                target = child
                break
        except Exception:
            pass
    if target is None:
        target = group.createChildGroup()
        target.createChildString("name", name)
        target.createChildString("value", str(value))
        try:
            target.createChildNumber("enabled", 1 if enabled else 0)
        except Exception:
            pass
    else:
        target.getChild("value").setValue(str(value), 0)
    return {"ok": True, "variable": name, "value": value}


# ---------------------------------------------------------------------------
# templates (JSON serialization of a node group)
# ---------------------------------------------------------------------------

def _capture_parameters(param, depth=0, max_depth=8):
    """Capture a parameter subtree as nested {name, value | children}."""
    entry = {"name": param.getName()}
    if param.getNumChildren() == 0 or depth >= max_depth:
        try:
            entry["value"] = param.getValue(0)
        except Exception:
            entry["skip"] = True
    else:
        entry["children"] = [_capture_parameters(c, depth + 1, max_depth)
                             for c in param.getChildren()]
    return entry


def _restore_parameters(captured, group, report):
    for entry in captured:
        name = entry.get("name")
        try:
            target = group.getChild(name)
        except Exception:
            target = None
        if target is None:
            report.append("missing parameter: %s" % name)
            continue
        if "value" in entry and not entry.get("skip"):
            try:
                target.setValue(entry["value"], 0)
            except Exception as e:
                report.append("could not set %s: %s" % (name, e))
        elif "children" in entry:
            _restore_parameters(entry["children"], target, report)


def cmd_export_template(paths=None, parent=None, include_connections=True,
                        name=None):
    """Serialize a set of sibling nodes (default: current selection, else all
    children of parent) into a JSON template dict."""
    NodegraphAPI = _nodegraph()
    if paths:
        nodes = [_resolve_node(p) for p in paths]
    else:
        selected = list(NodegraphAPI.GetAllSelectedNodes())
        nodes = selected if selected else list(
            _resolve_node(parent).getChildren())
    if not nodes:
        raise ValueError("Nothing to export: no paths given, no selection, "
                         "and parent has no children.")

    node_set = set(nodes)
    template_nodes = []
    for node in nodes:
        params = []
        try:
            params = [_capture_parameters(c)
                      for c in node.getParameters().getChildren()]
        except Exception:
            pass
        template_nodes.append({
            "name": node.getName(),
            "type": node.getType(),
            "position": _get_position(node),
            "parameters": params,
        })

    connections = []
    if include_connections:
        for node in nodes:
            for in_port in node.getInputPorts():
                try:
                    srcs = list(in_port.getConnectedPorts())
                except Exception:
                    srcs = []
                for src in srcs:
                    if src.getNode() in node_set:
                        connections.append({
                            "fromNode": src.getNode().getName(),
                            "fromPort": src.getName(),
                            "toNode": node.getName(),
                            "toPort": in_port.getName(),
                        })

    return {
        "ok": True,
        "template": {
            "name": name or "untitled",
            "format": "katana-mcp-template/1",
            "nodes": template_nodes,
            "connections": connections,
        },
    }


def cmd_apply_template(template, parent=None, offset_x=0, offset_y=0,
                       restore_parameters=True):
    NodegraphAPI = _nodegraph()
    if template.get("format") != "katana-mcp-template/1":
        raise ValueError("Unsupported template format: %r"
                         % template.get("format"))
    parent_node = _resolve_node(parent)
    name_map = {}
    created = []
    report = []

    for spec in template.get("nodes", []):
        node = NodegraphAPI.CreateNode(spec["type"], parent_node)
        try:
            node.setName(spec["name"])
        except Exception:
            pass
        name_map[spec["name"]] = node.getName()
        pos = spec.get("position")
        if pos:
            try:
                NodegraphAPI.SetNodePosition(
                    node, (pos[0] + float(offset_x),
                           pos[1] + float(offset_y)))
            except Exception:
                pass
        if restore_parameters and spec.get("parameters"):
            _restore_parameters(spec["parameters"], node.getParameters(),
                                report)
        created.append(_node_path(node))

    connected = 0
    for conn in template.get("connections", []):
        src_name = name_map.get(conn["fromNode"])
        dst_name = name_map.get(conn["toNode"])
        if not src_name or not dst_name:
            report.append("skipped connection %s -> %s (node missing)"
                          % (conn["fromNode"], conn["toNode"]))
            continue
        try:
            src = _resolve_node(src_name).getOutputPort(conn["fromPort"])
            dst = _resolve_node(dst_name).getInputPort(conn["toPort"])
            src.connect(dst)
            connected += 1
        except Exception as e:
            report.append("failed connection %s -> %s: %s"
                          % (conn["fromNode"], conn["toNode"], e))

    return {"ok": True, "created": created, "connections": connected,
            "warnings": report[:100]}


# ---------------------------------------------------------------------------
# scene graph (locations) - best effort
# ---------------------------------------------------------------------------

def cmd_get_scene_graph(root="/root/world", max_depth=3, max_nodes=500):
    try:
        from Katana import ScenegraphManager
    except Exception as e:
        return {"ok": False,
                "error": "ScenegraphManager unavailable: %s" % e}
    sg = None
    for getter in ("getActiveScenegraph", "getActiveSceneGraph"):
        fn = getattr(ScenegraphManager, getter, None)
        if fn:
            try:
                sg = fn()
                break
            except Exception:
                pass
    if sg is None:
        return {"ok": False,
                "error": "No active scene graph (is a node being viewed?)"}

    visited = [0]

    def build(location, path, depth):
        if visited[0] >= max_nodes:
            return None
        visited[0] += 1
        entry = {"path": path}
        try:
            entry["type"] = location.getType()
        except Exception:
            pass
        if depth < max_depth:
            children = []
            try:
                child_names = list(location.getChildNames())
            except Exception:
                try:
                    child_names = [c.getName()
                                   for c in location.getChildren()]
                except Exception:
                    child_names = []
            for child_name in child_names:
                child_path = path.rstrip("/") + "/" + child_name
                try:
                    child_loc = location.getChild(child_name)
                except Exception:
                    child_loc = None
                if child_loc is None:
                    children.append({"path": child_path})
                else:
                    sub = build(child_loc, child_path, depth + 1)
                    if sub:
                        children.append(sub)
                if visited[0] >= max_nodes:
                    break
            if children:
                entry["children"] = children
        return entry

    try:
        root_loc = sg.getLocation(root)
    except Exception:
        try:
            root_loc = sg.getRootLocation()
            root = "/root"
        except Exception as e:
            return {"ok": False, "error": "Cannot resolve %r: %s" % (root, e)}
    if root_loc is None:
        return {"ok": False, "error": "Location not found: %r" % root}
    tree = build(root_loc, root, 0)
    return {"ok": True, "truncated": visited[0] >= max_nodes, "tree": tree}


# ---------------------------------------------------------------------------
# render - best effort
# ---------------------------------------------------------------------------

def cmd_render_node(path, live=False):
    node = _resolve_node(path)
    try:
        from Katana import RenderManager
    except Exception as e:
        return {"ok": False,
                "error": "RenderManager module unavailable: %s" % e}
    candidates = (["StartLiveRender", "StartLiveRenderFromNode"] if live
                  else ["StartRender", "StartRenderFromNode",
                        "StartPreviewRender"])
    errors = []
    for fn_name in candidates:
        fn = getattr(RenderManager, fn_name, None)
        if not fn:
            continue
        for kwargs in ({"node": node}, {},):
            try:
                if kwargs:
                    fn(**kwargs)
                else:
                    fn(node)
                return {"ok": True, "method": fn_name, "live": live,
                        "node": _node_path(node)}
            except TypeError as e:
                errors.append("%s: %s" % (fn_name, e))
                continue
            except Exception as e:
                return {"ok": False,
                        "error": "%s failed: %s" % (fn_name, e)}
    return {"ok": False,
            "error": "No compatible render entry point found. Tried: %s"
                     % ("; ".join(errors) or ", ".join(candidates))}


# ---------------------------------------------------------------------------
# environment variables (inside the Katana process)
# ---------------------------------------------------------------------------

def cmd_get_env(name=None):
    import os
    if name:
        return {"ok": True, "name": name,
                "value": os.environ.get(name)}
    interesting = [k for k in sorted(os.environ)
                   if k.startswith(("KATANA", "OCIO", "ARNOLD", "RENDERMAN",
                                    "RMAN", "VRAY", "DELIGHT", "PATH",
                                    "PYTHONPATH", "LD_LIBRARY"))]
    return {"ok": True, "count": len(interesting),
            "env": {k: os.environ.get(k) for k in interesting}}


def cmd_set_env(name, value):
    import os
    old = os.environ.get(name)
    os.environ[name] = value
    return {"ok": True, "name": name, "previous": old, "value": value,
            "note": "Set inside the running Katana process only; does not "
                    "affect other sessions."}


# ---------------------------------------------------------------------------
# dispatch table
# ---------------------------------------------------------------------------

COMMANDS = {
    "ping": lambda: {"ok": True, "service": "katana-mcp"},
    "get_info": cmd_get_info,
    "exec": cmd_exec,
    "eval": cmd_eval,
    # node lifecycle
    "create_node": cmd_create_node,
    "delete_node": cmd_delete_node,
    "rename_node": cmd_rename_node,
    "duplicate_node": cmd_duplicate_node,
    "list_nodes": cmd_list_nodes,
    "get_node_tree": cmd_get_node_tree,
    "find_nodes": cmd_find_nodes,
    "get_node_info": cmd_get_node_info,
    "get_node_types": cmd_get_node_types,
    # selection & layout
    "select_nodes": cmd_select_nodes,
    "get_selected_nodes": cmd_get_selected_nodes,
    "set_node_position": cmd_set_node_position,
    "get_node_position": cmd_get_node_position,
    "arrange_nodes": cmd_arrange_nodes,
    # backdrop & notes
    "create_backdrop": cmd_create_backdrop,
    "set_node_note": cmd_set_node_note,
    "get_node_note": cmd_get_node_note,
    # parameters
    "set_parameter": cmd_set_parameter,
    "get_parameter": cmd_get_parameter,
    # connections
    "connect": cmd_connect,
    "disconnect": cmd_disconnect,
    # project
    "new_project": cmd_new_project,
    "open_project": cmd_open_project,
    "save_project": cmd_save_project,
    "get_project_settings": cmd_get_project_settings,
    "set_project_setting": cmd_set_project_setting,
    # GSV
    "get_gsv": cmd_get_gsv,
    "set_gsv": cmd_set_gsv,
    # templates
    "export_template": cmd_export_template,
    "apply_template": cmd_apply_template,
    # scene graph & render
    "get_scene_graph": cmd_get_scene_graph,
    "render_node": cmd_render_node,
    # environment
    "get_env": cmd_get_env,
    "set_env": cmd_set_env,
}
