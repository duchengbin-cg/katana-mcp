"""KatanaMCP - MCP bridge running inside Foundry Katana.

Exposes a JSON-RPC over TCP service so an external MCP server
(and therefore an AI assistant) can:

- read the Katana log stream
- execute Python inside Katana
- create / delete / inspect nodes
- get / set node parameters and connect ports
- verify actions against captured log output
"""

__version__ = "0.1.0"

DEFAULT_PORT = 17820
