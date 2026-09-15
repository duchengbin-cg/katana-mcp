"""In-memory ring-buffer capture of Katana log output.

Two capture channels are installed:

1. A ``logging.Handler`` attached to Python's root logger. Katana routes its
   own messages (``Katana.Logging``) through Python logging, so this catches
   INFO/WARNING/ERROR records from the application and from user scripts.

2. Tee wrappers around ``sys.stdout`` / ``sys.stderr``. Renderers and many
   Katana subsystems print directly to the console; teeing captures that
   output (including render logs) while still passing it through to the
   original streams.
"""

import collections
import logging
import sys
import threading
import time


class LogBuffer(object):
    """Thread-safe ring buffer of structured log entries."""

    def __init__(self, maxlen=5000):
        self._entries = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def add(self, level, source, message):
        message = message.rstrip("\n")
        if not message:
            return -1
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "time": time.strftime("%H:%M:%S"),
                "timestamp": time.time(),
                "level": level,
                "source": source,
                "message": message,
            }
            self._entries.append(entry)
            return self._seq

    def get(self, max_lines=200, min_level=None, since_seq=0):
        level_order = {"DEBUG": 10, "INFO": 20, "STDOUT": 20,
                       "WARNING": 30, "STDERR": 40, "ERROR": 40,
                       "CRITICAL": 50}
        threshold = level_order.get((min_level or "").upper(), 0)
        with self._lock:
            out = []
            for e in self._entries:
                if e["seq"] <= since_seq:
                    continue
                if level_order.get(e["level"], 20) < threshold:
                    continue
                out.append(dict(e))
        if max_lines and len(out) > max_lines:
            out = out[-max_lines:]
        return out

    def current_seq(self):
        with self._lock:
            return self._seq

    def clear(self):
        with self._lock:
            self._entries.clear()


class _LoggingHandler(logging.Handler):
    def __init__(self, buffer):
        super(_LoggingHandler, self).__init__()
        self._buffer = buffer

    def emit(self, record):
        try:
            self._buffer.add(record.levelname, record.name,
                             self.format(record))
        except Exception:
            pass


class _TeeStream(object):
    """File-like wrapper that tees written text into the log buffer."""

    def __init__(self, original, buffer, level, source):
        self._original = original
        self._buffer = buffer
        self._level = level
        self._source = source
        self._partial = ""

    def write(self, data):
        try:
            self._original.write(data)
        except Exception:
            pass
        self._partial += data
        while "\n" in self._partial:
            line, self._partial = self._partial.split("\n", 1)
            self._buffer.add(self._level, self._source, line)

    def flush(self):
        try:
            self._original.flush()
        except Exception:
            pass
        if self._partial:
            self._buffer.add(self._level, self._source, self._partial)
            self._partial = ""

    def __getattr__(self, name):
        return getattr(self._original, name)


_installed = False


def install(buffer):
    """Install the logging handler and stdout/stderr tees. Idempotent."""
    global _installed
    if _installed:
        return
    _installed = True

    handler = _LoggingHandler(buffer)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.DEBUG:
        root.setLevel(logging.DEBUG)

    # Also make sure the 'katana' logger propagates to root.
    katana_logger = logging.getLogger("katana")
    katana_logger.propagate = True

    if not isinstance(sys.stdout, _TeeStream):
        sys.stdout = _TeeStream(sys.stdout, buffer, "STDOUT", "stdout")
    if not isinstance(sys.stderr, _TeeStream):
        sys.stderr = _TeeStream(sys.stderr, buffer, "STDERR", "stderr")
