"""Qt binding compatibility shim (Katana 5-7 ship PySide2, Katana 8+ PySide6)."""

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    QT_BINDING = "PySide6"
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    QT_BINDING = "PySide2"
