# Changelog

## 0.2.1 (2026-09-16)

Katana 9.0 support pass (officially verified against Foundry's 9.0v1 specs:
Python 3.11.11, Qt/PySide 6.5.3, VFX Reference Platform CY2025, USD 25.08).

- `katana_status` now reports `pythonVersion` and `qtBinding` detected in
  the session
- `katana_get_env` also surfaces USD/PXR/FN_/MaterialX variables (Katana 9
  is USD-centric)
- README: compatibility matrix for Katana 5–9, Katana 9.0 notes (new
  UsdSuperLayer/UsdGaffer/UsdMaterial node types work via existing tools),
  launcher example updated to a Katana 9.0v1 path
- README: architecture diagram switched to mermaid, client list mentions
  Codex/ChatGPT

## 0.2.0 (2026-09-16)

Major feature expansion — the tool count grows from 17 to 45+.

**Katana-side commands (30 total):**
- Project: `katana_new_project`, `katana_open_project`, project settings
  read/write (`katana_get_project_settings` / `katana_set_project_setting`)
- Graph State Variables: `katana_get_gsv` / `katana_set_gsv`
- Node organization: `katana_get_node_tree`, `katana_find_nodes`,
  `katana_duplicate_node`, selection get/set, node positions,
  `katana_arrange_nodes` (layered auto-layout by connection depth)
- Backdrops & notes: `katana_create_backdrop`, `katana_set_node_note` /
  `katana_get_node_note`
- Templates: `katana_save_template` / `katana_apply_template` /
  `katana_list_templates` / `katana_delete_template` (JSON format captures
  node types, parameter values, positions and internal connections)
- Scene graph browsing: `katana_get_scene_graph`
- Render triggering: `katana_render_node` (best-effort across versions)
- Environment: `katana_get_env` / `katana_set_env` inside the Katana process
- `katana_execute_python` now also pre-imports `KatanaFile`

**Local scaffolding (runs without Katana):**
- `katana_create_launcher_bat` — Windows launcher with env vars,
  KATANA_RESOURCES, MCP autostart, optional project file
- `katana_scaffold_project_directory` — standard VFX project tree
- `katana_scaffold_supertool` — PackageSuperToolAPI Node.py + Qt Editor.py
- `katana_scaffold_panel_tool` — KatanaPanel tab skeleton
- `katana_scaffold_python_tool` — startup-menu or shelf-script tool

**Other:**
- Mock service gained a generic fallback handler for protocol smoke tests
- `katana_list_nodes` supports `recursive=True`

## 0.1.0 (2026-09-16)

Initial release: in-Katana plugin (menu + panel + threaded TCP service,
log capture), MCP server with 17 tools (logs, exec/eval, node CRUD,
parameters, connections, save, katana_verify), mock test service.
