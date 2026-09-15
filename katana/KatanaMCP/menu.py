"""Menu registration + optional auto-start.

Adds a "Katana MCP" entry to Katana's main menu bar with:
  - Open MCP Panel      (opens the tab)
  - Start Service       (starts on the default / env port)
  - Stop Service

Set environment variable KATANA_MCP_AUTOSTART=1 to start the service
automatically when Katana launches. KATANA_MCP_PORT overrides the port.
"""

import os

from . import DEFAULT_PORT
from .server import get_server

TAB_TYPE = "Katana MCP"


def _open_panel():
    from Katana import UI4
    try:
        UI4.App.Tabs.CreateTab(TAB_TYPE, True)
        return True
    except Exception:
        pass
    # Fallback: some versions expose floating tab creation
    try:
        UI4.App.Tabs.CreateFloatingTab(TAB_TYPE)
        return True
    except Exception:
        pass
    print("[katana-mcp] Could not open the tab automatically. "
          "Open it via Tabs > %s." % TAB_TYPE)
    return False


def _start_service():
    server = get_server()
    if server.running:
        print("[katana-mcp] Service already running on port %d"
              % server.port)
        return
    port = int(os.environ.get("KATANA_MCP_PORT", DEFAULT_PORT))
    server.start(port)
    print("[katana-mcp] Service started on 127.0.0.1:%d" % port)


def _stop_service():
    get_server().stop()
    print("[katana-mcp] Service stopped")


def register():
    try:
        from Katana import UI4
    except ImportError:
        return
    try:
        main_window = UI4.App.MainWindow.GetMainWindow()
        menu_bar = main_window.menuBar()
        menu = menu_bar.addMenu("Katana MCP")

        action = menu.addAction("Open MCP Panel")
        action.triggered.connect(_open_panel)

        action = menu.addAction("Start Service")
        action.triggered.connect(_start_service)

        action = menu.addAction("Stop Service")
        action.triggered.connect(_stop_service)
    except Exception as e:
        print("[katana-mcp] Menu registration failed: %s" % e)

    if os.environ.get("KATANA_MCP_AUTOSTART", "").lower() in ("1", "true",
                                                              "yes"):
        try:
            _start_service()
        except Exception as e:
            print("[katana-mcp] Auto-start failed: %s" % e)
