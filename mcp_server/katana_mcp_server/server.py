"""FastMCP server exposing Foundry Katana as MCP tools.

Run over stdio (standard for MCP clients):

    katana-mcp                    # entry point installed by the package
    python -m katana_mcp_server   # equivalent

Connection to Katana is configured via env vars:
    KATANA_MCP_HOST  (default 127.0.0.1)
    KATANA_MCP_PORT  (default 17820)

Template storage dir:
    KATANA_MCP_TEMPLATES_DIR  (default ~/.katana-mcp/templates)
"""

import json
import os
import re

from mcp.server.fastmcp import FastMCP

from .client import DEFAULT_HOST, DEFAULT_PORT, KatanaClient
from . import scaffold

mcp = FastMCP(
    "katana-mcp",
    instructions=(
        "Tools to control a running Foundry Katana session: read logs, "
        "execute Python, manage the node graph (create/edit/connect/"
        "organize nodes, backdrops, notes), manage project files and "
        "project settings, graph state variables, node templates, the "
        "scene graph, rendering, and local scaffolding (launchers, "
        "SuperTools, panels, project directories). "
        "Use katana_verify after actions to confirm no errors were logged."
    ),
)

_client = KatanaClient(
    host=os.environ.get("KATANA_MCP_HOST", DEFAULT_HOST),
    port=int(os.environ.get("KATANA_MCP_PORT", DEFAULT_PORT)),
)


def call(method, **params):
    return _client.call(method, **params)


# ===========================================================================
# status & logs
# ===========================================================================

@mcp.tool()
def katana_status() -> dict:
    """Check connectivity to Katana and return version/project info."""
    return call("get_info")


@mcp.tool()
def katana_get_logs(max_lines: int = 200, level: str = "",
                    clear: bool = False) -> dict:
    """Read captured Katana log entries (application messages, script and
    render output). Optionally filter by minimum level
    (DEBUG/INFO/WARNING/ERROR) and/or clear the buffer after reading."""
    return call("get_logs", max_lines=max_lines,
                min_level=level or None, clear=clear)


@mcp.tool()
def katana_clear_logs() -> dict:
    """Clear the in-Katana log capture buffer."""
    return call("clear_logs")


# ===========================================================================
# python execution
# ===========================================================================

@mcp.tool()
def katana_execute_python(code: str) -> dict:
    """Execute Python inside Katana's interpreter. NodegraphAPI, UI4, Utils
    and KatanaFile are pre-imported. Assign a variable named `result` to
    return a value. Returns stdout/stderr/result/error."""
    return call("exec", code=code)


@mcp.tool()
def katana_eval(expression: str) -> dict:
    """Evaluate a single Python expression inside Katana and return its
    value, e.g. "NodegraphAPI.GetRootNode().getName()"."""
    return call("eval", expression=expression)


# ===========================================================================
# node lifecycle & inspection
# ===========================================================================

@mcp.tool()
def katana_create_node(node_type: str, name: str = "",
                       parent: str = "") -> dict:
    """Create a node in Katana's node graph. node_type e.g. 'GafferThree',
    'Merge', 'CameraCreate'. Use katana_get_node_types to discover types.
    parent: group node path, empty = root level."""
    return call("create_node", node_type=node_type, name=name or None,
                parent=parent or None)


@mcp.tool()
def katana_delete_node(path: str) -> dict:
    """Delete a node by path (e.g. 'GafferThree1' or 'MyGroup/Merge1')."""
    return call("delete_node", path=path)


@mcp.tool()
def katana_rename_node(path: str, new_name: str) -> dict:
    """Rename a node."""
    return call("rename_node", path=path, new_name=new_name)


@mcp.tool()
def katana_duplicate_node(path: str, name: str = "") -> dict:
    """Duplicate a node including its parameters and incoming connections."""
    return call("duplicate_node", path=path, name=name or None)


@mcp.tool()
def katana_list_nodes(parent: str = "", recursive: bool = False) -> dict:
    """List child nodes of a parent (empty = root). recursive=True walks
    into groups."""
    return call("list_nodes", parent=parent or None, recursive=recursive)


@mcp.tool()
def katana_get_node_tree(parent: str = "", max_depth: int = 4) -> dict:
    """Get the node graph as a nested tree (name/type/path/children)."""
    return call("get_node_tree", parent=parent or None, max_depth=max_depth)


@mcp.tool()
def katana_find_nodes(name_contains: str = "", node_type: str = "",
                      parent: str = "") -> dict:
    """Search nodes by name substring and/or exact node type, recursively."""
    return call("find_nodes", name_contains=name_contains or None,
                node_type=node_type or None, parent=parent or None)


@mcp.tool()
def katana_get_node_info(path: str) -> dict:
    """Get a node's type, position, ports and full parameter listing."""
    return call("get_node_info", path=path)


@mcp.tool()
def katana_get_node_types(filter: str = "") -> dict:
    """List node types registered in this Katana session, optionally filtered
    by substring (e.g. 'Gaffer', 'Render', 'Arnold')."""
    return call("get_node_types", filter=filter or None)


# ===========================================================================
# selection & layout
# ===========================================================================

@mcp.tool()
def katana_select_nodes(paths: list[str], exclusive: bool = True) -> dict:
    """Set the node graph selection to the given node paths."""
    return call("select_nodes", paths=paths, exclusive=exclusive)


@mcp.tool()
def katana_get_selected_nodes() -> dict:
    """Return the currently selected nodes in the node graph."""
    return call("get_selected_nodes")


@mcp.tool()
def katana_set_node_position(path: str, x: float, y: float) -> dict:
    """Set a node's position in the node graph."""
    return call("set_node_position", path=path, x=x, y=y)


@mcp.tool()
def katana_arrange_nodes(paths: list[str] | None = None,
                         direction: str = "horizontal",
                         x_spacing: int = 260, y_spacing: int = 120) -> dict:
    """Auto-layout nodes into layers by connection depth. Uses the given
    paths, else the current selection, else all root-level nodes. direction:
    'horizontal' (layers as columns) or 'vertical'."""
    return call("arrange_nodes", paths=paths, direction=direction,
                x_spacing=x_spacing, y_spacing=y_spacing)


# ===========================================================================
# backdrop & notes
# ===========================================================================

@mcp.tool()
def katana_create_backdrop(text: str = "", x: float = 0, y: float = 0,
                           width: float | None = None,
                           height: float | None = None,
                           name: str = "") -> dict:
    """Create a Backdrop node for visually grouping an area of the node
    graph, with optional text, position and size."""
    return call("create_backdrop", text=text, x=x, y=y, width=width,
                height=height, name=name or None)


@mcp.tool()
def katana_set_node_note(path: str, note: str) -> dict:
    """Attach a text note/annotation to any node (stored as a user
    parameter 'mcpNote', survives saving the project)."""
    return call("set_node_note", path=path, note=note)


@mcp.tool()
def katana_get_node_note(path: str) -> dict:
    """Read the note previously attached to a node via katana_set_node_note."""
    return call("get_node_note", path=path)


# ===========================================================================
# parameters
# ===========================================================================

@mcp.tool()
def katana_set_parameter(node_path: str, parameter: str, value,
                         time: float = 0) -> dict:
    """Set a node parameter. Use dot paths for nested parameters, e.g.
    'resolution.x', 'lightList.0.intensity'. value must be JSON-native."""
    return call("set_parameter", node_path=node_path, parameter=parameter,
                value=value, time=time)


@mcp.tool()
def katana_get_parameter(node_path: str, parameter: str,
                         time: float = 0) -> dict:
    """Read a node parameter value."""
    return call("get_parameter", node_path=node_path, parameter=parameter,
                time=time)


# ===========================================================================
# connections
# ===========================================================================

@mcp.tool()
def katana_connect_nodes(source: str, target: str, source_port: str = "",
                         target_port: str = "") -> dict:
    """Connect source node's output to target node's input. Port names
    optional (defaults: first ports)."""
    return call("connect", source=source, target=target,
                source_port=source_port or None,
                target_port=target_port or None)


@mcp.tool()
def katana_disconnect_nodes(source: str, target: str) -> dict:
    """Remove all connections between two nodes."""
    return call("disconnect", source=source, target=target)


# ===========================================================================
# project files & project settings
# ===========================================================================

@mcp.tool()
def katana_new_project() -> dict:
    """Start a new empty Katana project (discards unsaved changes)."""
    return call("new_project")


@mcp.tool()
def katana_open_project(path: str) -> dict:
    """Open a .katana project file. WARNING: discards unsaved changes."""
    return call("open_project", path=path)


@mcp.tool()
def katana_save_project(path: str = "") -> dict:
    """Save the current project; optionally to a new file path."""
    return call("save_project", path=path or None)


@mcp.tool()
def katana_get_project_settings() -> dict:
    """Read all Project Settings (frame range, resolution, etc. - the
    parameters from Katana's Project Settings tab)."""
    return call("get_project_settings")


@mcp.tool()
def katana_set_project_setting(name: str, value, time: float = 0) -> dict:
    """Set one Project Setting by name, e.g. 'inTime', 'outTime',
    'resolution'. Unknown names return the list of valid settings."""
    return call("set_project_setting", name=name, value=value, time=time)


# ===========================================================================
# graph state variables
# ===========================================================================

@mcp.tool()
def katana_get_gsv() -> dict:
    """List all Graph State Variables and their current values."""
    return call("get_gsv")


@mcp.tool()
def katana_set_gsv(name: str, value: str, enabled: bool = True) -> dict:
    """Create or update a Graph State Variable (e.g. shot, pass, lod)."""
    return call("set_gsv", name=name, value=value, enabled=enabled)


# ===========================================================================
# templates
# ===========================================================================

@mcp.tool()
def katana_save_template(name: str, paths: list[str] | None = None,
                         parent: str = "") -> dict:
    """Export nodes (given paths, else current selection, else all
    root-level nodes) as a reusable local template. Captures node types,
    parameter values, positions and internal connections."""
    result = call("export_template", paths=paths, parent=parent or None,
                  include_connections=True, name=name)
    template = result["template"]
    path = scaffold.template_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(template, fh, indent=2)
    return {"ok": True, "templatePath": path,
            "nodeCount": len(template["nodes"]),
            "connectionCount": len(template["connections"])}


@mcp.tool()
def katana_list_templates() -> dict:
    """List locally saved node templates."""
    directory = scaffold.default_templates_dir()
    if not os.path.isdir(directory):
        return {"ok": True, "templates": []}
    templates = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".json"):
            continue
        fpath = os.path.join(directory, fname)
        try:
            with open(fpath, encoding="utf-8") as fh:
                data = json.load(fh)
            templates.append({
                "name": fname[:-5],
                "nodeCount": len(data.get("nodes", [])),
                "nodeTypes": sorted({n.get("type", "?")
                                     for n in data.get("nodes", [])}),
            })
        except Exception:
            templates.append({"name": fname[:-5], "error": "unreadable"})
    return {"ok": True, "templates": templates}


@mcp.tool()
def katana_apply_template(name: str, parent: str = "", offset_x: float = 0,
                          offset_y: float = 0) -> dict:
    """Instantiate a saved template into the node graph (nodes, parameter
    values and internal connections are recreated)."""
    path = scaffold.template_path(name)
    if not os.path.isfile(path):
        return {"ok": False,
                "error": "Template %r not found. Use katana_list_templates."
                         % name}
    with open(path, encoding="utf-8") as fh:
        template = json.load(fh)
    return call("apply_template", template=template, parent=parent or None,
                offset_x=offset_x, offset_y=offset_y)


@mcp.tool()
def katana_delete_template(name: str) -> dict:
    """Delete a locally saved template."""
    path = scaffold.template_path(name)
    if not os.path.isfile(path):
        return {"ok": False, "error": "Template %r not found" % name}
    os.remove(path)
    return {"ok": True, "deleted": name}


# ===========================================================================
# scene graph & render
# ===========================================================================

@mcp.tool()
def katana_get_scene_graph(root: str = "/root/world", max_depth: int = 3,
                           max_nodes: int = 500) -> dict:
    """Browse scene graph locations (requires a viewed node producing a
    scene). Returns a nested tree of location paths and types."""
    return call("get_scene_graph", root=root, max_depth=max_depth,
                max_nodes=max_nodes)


@mcp.tool()
def katana_render_node(path: str, live: bool = False) -> dict:
    """Trigger a render of a node (e.g. a Render node). live=True attempts a
    Live Render instead. Follow up with katana_get_logs/katana_verify to
    check render output."""
    return call("render_node", path=path, live=live)


# ===========================================================================
# environment (inside the Katana process)
# ===========================================================================

@mcp.tool()
def katana_get_env(name: str = "") -> dict:
    """Read environment variables of the running Katana process. Without a
    name, returns the interesting ones (KATANA_*, OCIO, renderer vars...)."""
    return call("get_env", name=name or None)


@mcp.tool()
def katana_set_env(name: str, value: str) -> dict:
    """Set an environment variable inside the running Katana process
    (does not affect other sessions or future launches - use
    katana_create_launcher_bat for persistent environments)."""
    return call("set_env", name=name, value=value)


# ===========================================================================
# verification
# ===========================================================================

_DEFAULT_ERROR_RE = re.compile(
    r"(Traceback \(most recent call last\)|\berror\b|\bfailed\b|"
    r"\bexception\b|ERROR|CRITICAL)", re.IGNORECASE)


@mcp.tool()
def katana_verify(code: str = "", error_pattern: str = "",
                  scan_lines: int = 500) -> dict:
    """Verify an action succeeded by scanning the logs it produced.

    1. Snapshot the current log position
    2. (optional) execute `code` inside Katana
    3. Scan all log entries produced since the snapshot for errors

    Returns success=true only when execution raised no exception and no
    error-pattern log entries appeared. error_pattern is an optional custom
    regex replacing the default error detection."""
    marker = call("log_seq")["currentSeq"]
    exec_result = None
    if code:
        exec_result = call("exec", code=code)
    logs = call("get_logs", max_lines=scan_lines, since_seq=marker)
    entries = logs.get("entries", [])
    regex = (re.compile(error_pattern, re.IGNORECASE) if error_pattern
             else _DEFAULT_ERROR_RE)
    matched = [e for e in entries
               if e.get("level") in ("ERROR", "CRITICAL")
               or regex.search(e.get("message", ""))]
    success = (not matched) and (exec_result is None
                                 or exec_result.get("ok"))
    return {
        "success": success,
        "execResult": exec_result,
        "newLogEntries": len(entries),
        "matchedErrors": matched[:50],
    }


# ===========================================================================
# local scaffolding (no Katana connection required)
# ===========================================================================

@mcp.tool()
def katana_create_launcher_bat(katana_exe: str, output_path: str,
                               project_path: str = "",
                               env_vars: dict | None = None,
                               katana_resources: list[str] | None = None,
                               mcp_autostart: bool = True,
                               extra_args: str = "") -> dict:
    """Generate a Windows .bat that sets environment variables (renderer
    paths, OCIO, KATANA_RESOURCES, MCP autostart...) and launches Katana,
    optionally opening a project. Example katana_exe:
    'C:/Program Files/Katana9.0v1/bin/katanaBin.exe'"""
    return scaffold.create_launcher_bat(
        katana_exe=katana_exe, output_path=output_path,
        project_path=project_path or None, env_vars=env_vars,
        katana_resources=katana_resources, mcp_autostart=mcp_autostart,
        extra_args=extra_args or None)


@mcp.tool()
def katana_scaffold_project_directory(base_path: str,
                                      extra_dirs: list[str] | None = None
                                      ) -> dict:
    """Create a standard VFX project directory tree (assets/models,
    lookdev, lighting/templates, renders, comp, scripts, ...)."""
    return scaffold.scaffold_project_directory(base_path,
                                               extra_dirs=extra_dirs)


@mcp.tool()
def katana_scaffold_supertool(name: str, base_directory: str) -> dict:
    """Generate a SuperTool skeleton (PackageSuperToolAPI Node.py + Qt
    Editor.py) under <base_directory>/SuperTools/<name>/. Add
    base_directory to KATANA_RESOURCES to load it."""
    return scaffold.scaffold_supertool(name, base_directory)


@mcp.tool()
def katana_scaffold_panel_tool(name: str, base_directory: str) -> dict:
    """Generate a Katana panel (tab) skeleton under <base_directory>/Tabs/.
    Add base_directory to KATANA_RESOURCES to load it."""
    return scaffold.scaffold_panel_tool(name, base_directory)


@mcp.tool()
def katana_scaffold_python_tool(name: str, base_directory: str,
                                kind: str = "startup") -> dict:
    """Generate a Python tool skeleton. kind='startup': auto-registered
    menu entry (<base>/Startup/). kind='shelf': importable script tool
    (<base>/Scripts/)."""
    if kind not in ("startup", "shelf"):
        return {"ok": False, "error": "kind must be 'startup' or 'shelf'"}
    return scaffold.scaffold_python_tool(name, base_directory, kind=kind)


# ===========================================================================
# knowledge / skill guides
# ===========================================================================

def _read_skill_doc(filename):
    """Read a bundled skill guide, works both from an installed package
    (importlib.resources) and from a raw source checkout."""
    try:
        from importlib import resources
        ref = resources.files("katana_mcp_server").joinpath(
            "skills", filename)
        return ref.read_text(encoding="utf-8")
    except Exception:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(here, "skills", filename),
        os.path.join(here, os.pardir, os.pardir, "skills", filename),
    ):
        candidate = os.path.normpath(candidate)
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8") as fh:
                return fh.read()
    return ("Skill guide '%s' not found. Reinstall katana-mcp or check "
            "the skills/ directory in the repository." % filename)


@mcp.tool()
def get_lookdev_skill_guide() -> str:
    """Get the Katana LookDev construction guide: standard node-graph
    topology, the node-type/parameter registry, CEL best practices, a
    verified NodegraphAPI Python blueprint and known pitfalls. You MUST
    call this tool before creating or editing a LookDev node graph so
    that generated code follows the specification."""
    return _read_skill_doc("katana_lookdev_skill.md")


# ===========================================================================
# entry point
# ===========================================================================

def main():
    mcp.run()


if __name__ == "__main__":
    main()
