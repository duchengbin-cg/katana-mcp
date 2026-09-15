# katana-mcp

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) bridge for
**Foundry Katana**. Katana does not ship an official MCP interface — this
project adds one, so AI assistants (Claude, WorkBuddy, Cursor, ...) can talk
directly to a running Katana session:

- **Read logs** — application messages, script output and render output
  printed to the console, captured in a ring buffer inside Katana
- **Execute Python** inside Katana's interpreter (with `NodegraphAPI`, `UI4`,
  `Utils` pre-imported)
- **Create / delete / rename / inspect nodes** in the node graph
- **Get / set node parameters** (including nested parameters via dot paths)
- **Connect / disconnect node ports**
- **Verify results against the logs** — run an action, then automatically
  scan the log output it produced for errors, warnings and tracebacks

## Architecture

Two components:

```
┌────────────────────────┐      JSON-lines over TCP       ┌───────────────────────┐      stdio (MCP)     ┌─────────────┐
│  Foundry Katana        │      127.0.0.1:17820           │  katana-mcp server    │                      │  AI client  │
│  (KatanaMCP plugin:    │ ◄────────────────────────────► │  (Python / FastMCP)   │ ◄──────────────────► │  Claude /   │
│   menu + panel + TCP   │                                │  tool bridge          │                      │  WorkBuddy  │
│   service + log buffer)│                                │                       │                      │  ...        │
└────────────────────────┘                                └───────────────────────┘                      └─────────────┘
```

- `katana/` — the in-Katana plugin. Adds a **Katana MCP** main-menu entry and
  a **Katana MCP** tab (panel) with Start/Stop controls, port setting and a
  live log view. The service only listens on `127.0.0.1`.
- `mcp_server/` — the MCP server package your AI client launches. It connects
  to the in-Katana service and exposes everything as MCP tools.

## Installation

### 1. Katana side (plugin)

Add the `katana/` directory of this repository to your `KATANA_RESOURCES`
environment variable (semicolon-separated on Windows, colon on Linux):

```powershell
# Windows example
$env:KATANA_RESOURCES = "C:\path\to\katana-mcp\katana;$env:KATANA_RESOURCES"
```

```bash
# Linux example
export KATANA_RESOURCES=/path/to/katana-mcp/katana:$KATANA_RESOURCES
```

Launch Katana. You should see a **Katana MCP** menu and be able to open the
panel via the menu entry or `Tabs > Katana MCP`. Click **Start MCP Service**
(default port `17820`).

Optional environment variables:

| Variable              | Effect                                        |
|-----------------------|-----------------------------------------------|
| `KATANA_MCP_AUTOSTART`| Set to `1` to start the service on launch     |
| `KATANA_MCP_PORT`     | Default port (fallback: `17820`)              |

### 2. MCP server side (AI client)

No manual install needed if your client supports `uvx`. Add this to your MCP
configuration (e.g. Claude Desktop `claude_desktop_config.json`, or
WorkBuddy's `~/.workbuddy/mcp.json`):

```json
{
  "mcpServers": {
    "katana": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/duchengbin-cg/katana-mcp#subdirectory=mcp_server",
        "katana-mcp"
      ]
    }
  }
}
```

Or install from a local checkout:

```bash
pip install -e ./mcp_server
# then configure your client with:
#   "command": "katana-mcp"
```

Connection settings (env vars for the MCP server process):

| Variable          | Default       |
|-------------------|---------------|
| `KATANA_MCP_HOST` | `127.0.0.1`   |
| `KATANA_MCP_PORT` | `17820`       |

## Tools exposed to the AI

| Tool | Purpose |
|---|---|
| `katana_status` | Connectivity check + Katana/project info |
| `katana_get_logs` / `katana_clear_logs` | Read / clear captured log entries (level filter supported) |
| `katana_execute_python` | Run Python inside Katana (`result` variable is returned) |
| `katana_eval` | Evaluate one expression and return its value |
| `katana_create_node` / `katana_delete_node` / `katana_rename_node` | Node lifecycle |
| `katana_list_nodes` / `katana_get_node_info` / `katana_get_node_types` | Scene inspection |
| `katana_set_parameter` / `katana_get_parameter` | Parameter editing (dot paths for nesting) |
| `katana_connect_nodes` / `katana_disconnect_nodes` | Port wiring |
| `katana_save_project` | Save the `.katana` file |
| `katana_verify` | Execute code (optional) and scan the logs it produced for errors — the "did it actually work?" tool |

### Typical AI workflow

> "Create a GafferThree, connect it to a Merge, set the merge to passthrough
> and verify nothing errored."

The assistant will call `katana_create_node` ×2, `katana_connect_nodes`,
`katana_set_parameter`, then `katana_verify` — which returns `success: true`
only if the action produced no error-level log entries or tracebacks.

## Testing without Katana

A mock service speaks the same wire protocol:

```bash
python scripts/mock_katana.py   # listens on 127.0.0.1:17820
```

Point the MCP server at it and all connection/log/tool plumbing can be
developed without launching Katana.

## Security notes

- The in-Katana service binds to **127.0.0.1 only** by design.
- `katana_execute_python` runs arbitrary code inside Katana — that is the
  point of the tool, but treat the MCP server as trusted, same as giving
  someone access to Katana's Python shelf.

## Compatibility

- Katana 5.x – 8.x (Qt shim covers PySide2 and PySide6)
- MCP server: Python ≥ 3.9, depends only on the official `mcp` package

## Roadmap

- Scene graph (location) browsing via `ScenegraphManager`
- Render triggering + render log streaming
- Expression / CEL helpers
- Project open/new operations

Contributions welcome — issues and PRs please!

## License

MIT
