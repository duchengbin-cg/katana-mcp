"""Katana tab registration for the Katana MCP panel.

Katana discovers tabs via the PluginRegistry tuple:
    (pluginType, version, tabName, callable)
"""

import os
import sys

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _HERE not in sys.path:
    sys.path.append(_HERE)

from KatanaMCP.panel import KatanaMCPPanel

PluginRegistry = [("KatanaPanel", 2, "Katana MCP", KatanaMCPPanel)]
