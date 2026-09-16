# katana-mcp (MCP server package)

The MCP server half of [katana-mcp](https://github.com/duchengbin-cg/katana-mcp).
Your AI client launches this package over stdio; it connects to the
in-Katana bridge plugin (see the repository root README for the full
architecture and installation guide).

Besides the Katana control tools, the server bundles
**skill guides** — distilled, verified Katana knowledge that AI clients
should read before generating node-graph code:

- `get_lookdev_skill_guide` — standard LookDev topology, node registry,
  CEL patterns, a verified `NodegraphAPI` blueprint and pitfalls
  (source: `skills/katana_lookdev_skill.md`, analyzed from 42 official
  Katana example projects).

## Install

```bash
pip install .
# or, from the repository root:
#   uvx --from "git+https://github.com/duchengbin-cg/katana-mcp#subdirectory=mcp_server" katana-mcp
```

Connection env vars: `KATANA_MCP_HOST` (default `127.0.0.1`),
`KATANA_MCP_PORT` (default `17820`).
