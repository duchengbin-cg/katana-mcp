"""Qt binding compatibility shim.

Katana 5.x - 7.x ship PySide2 (Qt 5), Katana 8.x and 9.x ship PySide6
(Katana 9.0v1: Qt 6.5.3 / PySide 6.5.3, VFX Reference Platform CY2025).
"""

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    QT_BINDING = "PySide6"
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    QT_BINDING = "PySide2"

