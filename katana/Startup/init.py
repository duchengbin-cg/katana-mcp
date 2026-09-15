"""Katana startup hook: registers the Katana MCP menu (and optional autostart)."""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.append(_HERE)

try:
    from KatanaMCP import menu
    menu.register()
except Exception as _e:
    print("[katana-mcp] Startup failed: %s" % _e)
