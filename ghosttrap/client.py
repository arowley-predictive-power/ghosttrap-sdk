"""Drop-in error reporter for ghosttrap.io.

Usage:
    import ghosttrap

    # with a token (recommended):
    ghosttrap.init("t_abc123def456")

    # or with a full URL:
    ghosttrap.init("https://ghosttrap.io/trap/owner/repo/")

Unhandled exceptions are posted automatically via sys.excepthook. For
caught exceptions inside web frameworks, call ghosttrap.report(exc)
explicitly inside the except block.
"""

import json
import sys
import traceback
import urllib.request

GHOSTTRAP_SERVER = "https://ghosttrap.io"

_endpoint = None
_original_excepthook = None


def init(dsn, server=None):
    """Configure the reporter.

    Args:
        dsn: Either a token (e.g. "t_abc123") or a full URL
             (e.g. "https://ghosttrap.io/trap/owner/repo/")
        server: Base server URL. Only needed if dsn is a token and
                you're not using ghosttrap.io.
    """
    global _endpoint, _original_excepthook
    if dsn.startswith("http://") or dsn.startswith("https://"):
        _endpoint = dsn.rstrip("/") + "/"
    else:
        base = (server or GHOSTTRAP_SERVER).rstrip("/")
        _endpoint = f"{base}/trap/{dsn}/"
    _original_excepthook = sys.excepthook
    sys.excepthook = _error_hook


def report(exc):
    """Report a caught exception to the ghosttrap server.

    Args:
        exc: the exception instance from an `except Exception as exc` block
    """
    if _endpoint is None:
        return
    _post(_build_payload(type(exc), exc, exc.__traceback__))


def _error_hook(exc_type, exc_value, exc_tb):
    _post(_build_payload(exc_type, exc_value, exc_tb))
    _original_excepthook(exc_type, exc_value, exc_tb)


def _build_payload(exc_type, exc_value, exc_tb):
    frames = traceback.extract_tb(exc_tb)
    return {
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
    }


def _post(payload):
    try:
        req = urllib.request.Request(
            _endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
