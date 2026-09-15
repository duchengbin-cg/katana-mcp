"""Katana tab panel: start/stop the MCP service and watch the log stream."""

import os

from . import DEFAULT_PORT
from .qtcompat import QtCore, QtWidgets
from .server import get_server


class KatanaMCPPanel(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(KatanaMCPPanel, self).__init__(parent)
        self._server = get_server()
        self._build_ui()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._last_seq = self._server.log_buffer.current_seq()
        self._refresh_status()

    # -- UI ---------------------------------------------------------------

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Port:"))
        self._port_spin = QtWidgets.QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(int(os.environ.get("KATANA_MCP_PORT",
                                                    DEFAULT_PORT)))
        row.addWidget(self._port_spin)

        self._toggle_btn = QtWidgets.QPushButton("Start MCP Service")
        self._toggle_btn.clicked.connect(self._on_toggle)
        row.addWidget(self._toggle_btn)

        self._status_label = QtWidgets.QLabel("Stopped")
        row.addWidget(self._status_label)
        row.addStretch(1)
        layout.addLayout(row)

        hint = QtWidgets.QLabel(
            "Point your MCP client (Claude / WorkBuddy / ...) at the "
            "katana-mcp server package and keep Katana running. "
            "The service listens on 127.0.0.1 only.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        layout.addWidget(QtWidgets.QLabel("Captured log (auto-refresh):"))
        self._log_view = QtWidgets.QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumBlockCount(2000)
        layout.addWidget(self._log_view)

        btn_row = QtWidgets.QHBoxLayout()
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._log_view.clear)
        btn_row.addStretch(1)
        btn_row.addWidget(clear_btn)
        layout.addLayout(btn_row)

    # -- behaviour ----------------------------------------------------------

    def _on_toggle(self):
        if self._server.running:
            self._server.stop()
        else:
            try:
                self._server.start(self._port_spin.value())
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self, "Katana MCP", "Failed to start service:\n%s" % e)
        self._refresh_status()

    def _refresh_status(self):
        running = self._server.running
        self._toggle_btn.setText("Stop MCP Service" if running
                                 else "Start MCP Service")
        self._port_spin.setEnabled(not running)
        if running:
            self._status_label.setText(
                "Running on 127.0.0.1:%d" % self._server.port)
            self._status_label.setStyleSheet("color: #7ec97e;")
        else:
            self._status_label.setText("Stopped")
            self._status_label.setStyleSheet("color: gray;")

    def _refresh(self):
        self._refresh_status()
        entries = self._server.log_buffer.get(max_lines=500,
                                              since_seq=self._last_seq)
        for e in entries:
            self._last_seq = max(self._last_seq, e["seq"])
            self._log_view.appendPlainText(
                "[%s] %-8s %s" % (e["time"], e["level"], e["message"]))


# Katana tab registration expects a class it can instantiate with a parent.
def make_tab(parent=None):
    return KatanaMCPPanel(parent)
