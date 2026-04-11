"""Drop-in error catcher for Python apps.

Usage:
    import ghosttrap
    ghosttrap.init("https://ghosttrap.io/trap/<your-token>")

Unhandled exceptions are posted to the receiver with full tracebacks.
The original excepthook is preserved so errors still print to stderr
as normal.
"""

import json
import sys
import traceback
import urllib.request

_dsn = None
_original_excepthook = None


def _error_hook(exc_type, exc_value, exc_tb):
    try:
        frames = traceback.extract_tb(exc_tb)
        payload = json.dumps({
            "type": exc_type.__name__,
            "message": str(exc_value),
            "traceback": traceback.format_exception(exc_type, exc_value, exc_tb),
            "frames": [
                {
                    "file": f.filename,
                    "line": f.lineno,
                    "function": f.name,
                    "code": f.line,
                }
                for f in frames
            ],
        }).encode()

        req = urllib.request.Request(
            _dsn,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    _original_excepthook(exc_type, exc_value, exc_tb)


def init(dsn):
    """Install the error catcher.

    Args:
        dsn: Full URL of your ghosttrap receiver endpoint, e.g.
             "https://ghosttrap.io/trap/abc123"
    """
    global _dsn, _original_excepthook
    _dsn = dsn.rstrip("/")
    _original_excepthook = sys.excepthook
    sys.excepthook = _error_hook
