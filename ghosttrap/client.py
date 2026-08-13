"""Drop-in error reporter for ghosttrap.io.

Usage:
    import ghosttrap

    # with a token (recommended):
    ghosttrap.init("t_abc123def456")

    # or with a full URL:
    ghosttrap.init("https://ghosttrap.io/trap/owner/repo/")

Hooks into sys.excepthook (unhandled exceptions), threading.excepthook
(unhandled exceptions in background threads), Python logging
(logger.exception / logger.error with exc_info), and Celery task
failures (if Celery is installed). Django apps should add
ghosttrap.django.GhostTrapApp to INSTALLED_APPS and
ghosttrap.django.GhostTrapMiddleware to MIDDLEWARE. To report a
caught exception or a non-exception condition, call ghosttrap.trap().
"""

import json
import logging
import os
import socket
import sys
import threading
import traceback
import urllib.request

GHOSTTRAP_SERVER = "https://ghosttrap.io"

_endpoint = None
_original_excepthook = None
_original_threading_excepthook = None
_server_name = None
_send_user = False
_trap_logs = False
_channel = "service"


def _detect_channel():
    """Classify how this process was started.

    "adhoc" marks code that has no home in the repo — a REPL,
    `manage.py shell`/`shell_plus`, `python -c`, or piped stdin. Errors
    from adhoc processes are shelved server-side (pull-only, never
    streamed): their author already watched them fail, so streaming them
    would only wake the repo's agent for code it cannot open or fix.
    Override with GHOSTTRAP_CHANNEL=service|adhoc.
    """
    env = os.environ.get("GHOSTTRAP_CHANNEL", "").strip().lower()
    if env in ("service", "adhoc"):
        return env
    argv = sys.argv or [""]
    if os.path.basename(argv[0] or "") == "manage.py" \
            and len(argv) > 1 and argv[1] in ("shell", "shell_plus"):
        return "adhoc"
    if argv[0] in ("-c", "-", ""):
        return "adhoc"
    if sys.flags.interactive or hasattr(sys, "ps1"):
        return "adhoc"
    return "service"


def init(dsn, server=None, send_user=False, trap_logs=False):
    """Configure the reporter.

    Args:
        dsn: Either a token (e.g. "t_abc123") or a full URL
             (e.g. "https://ghosttrap.io/trap/owner/repo/")
        server: Base server URL. Only needed if dsn is a token and
                you're not using ghosttrap.io.
        send_user: If True, the Django integration attaches the
                authenticated user's id and username to reported errors.
                Default False — user data is PII and stays out of
                payloads unless you opt in.
        trap_logs: If True, logger.error() / logger.critical() calls
                that carry no exception are reported too, as type
                LoggedError / LoggedCritical with the log call site as
                the frame. Default False — in chatty codebases every
                error-level log line becomes an event, which floods.

    Environment: GHOSTTRAP_DISABLE=1 makes init() a no-op for this
    process. GHOSTTRAP_CHANNEL=service|adhoc forces the reporting
    channel instead of auto-detection (see _detect_channel).
    """
    global _endpoint, _original_excepthook, _original_threading_excepthook, \
        _server_name, _send_user, _trap_logs, _channel
    if os.environ.get("GHOSTTRAP_DISABLE", "").strip().lower() in ("1", "true", "yes"):
        return
    _channel = _detect_channel()
    if dsn.startswith("http://") or dsn.startswith("https://"):
        _endpoint = dsn.rstrip("/") + "/"
    else:
        base = (server or GHOSTTRAP_SERVER).rstrip("/")
        _endpoint = f"{base}/trap/{dsn}/"
    try:
        _server_name = socket.gethostname() or None
    except Exception:
        _server_name = None
    _send_user = bool(send_user)
    _trap_logs = bool(trap_logs)
    _original_excepthook = sys.excepthook
    sys.excepthook = _error_hook
    _original_threading_excepthook = threading.excepthook
    threading.excepthook = _thread_hook
    _install_logging_handler()
    _install_celery_hook()


def report(exc, user=None):
    """Report a caught exception. Kept for backward compatibility; prefer `trap`."""
    trap(exc, user=user)


def trap(exc_or_message, user=None):
    """Manually trap an event.

    Pass an exception instance to report a caught error (its type, message,
    and traceback are sent). Pass a string to report a synthetic event with
    the caller's current stack — labelled `TrappedEvent` so it's distinct
    from real exceptions.

    Args:
        exc_or_message: exception instance or string
        user: optional dict with user context (id, username). Only sent
              if init() was called with send_user=True.
    """
    if _endpoint is None:
        return
    if isinstance(exc_or_message, BaseException):
        exc = exc_or_message
        _post(_build_payload(type(exc), exc, exc.__traceback__, user=user))
    else:
        _post(_build_synthetic_payload(str(exc_or_message), user=user))


def _error_hook(exc_type, exc_value, exc_tb):
    _post(_build_payload(exc_type, exc_value, exc_tb))
    _original_excepthook(exc_type, exc_value, exc_tb)


def _thread_hook(args):
    # sys.excepthook never fires for threads; Python routes them here instead.
    # SystemExit in a thread is a normal way to stop one — the stdlib hook
    # ignores it silently, and so do we.
    if args.exc_type is not SystemExit:
        _post(_build_payload(args.exc_type, args.exc_value, args.exc_traceback))
    _original_threading_excepthook(args)


def _install_logging_handler():
    handler = _GhostTrapLogHandler()
    handler.setLevel(logging.ERROR)
    logging.getLogger().addHandler(handler)


def _install_celery_hook():
    try:
        from celery.signals import task_failure
        task_failure.connect(_on_task_failure)
    except ImportError:
        pass


def _on_task_failure(sender, exception, traceback, **kwargs):
    report(exception)


class _GhostTrapLogHandler(logging.Handler):
    def emit(self, record):
        if record.exc_info and record.exc_info[1]:
            report(record.exc_info[1])
        elif _trap_logs:
            _post(_build_logged_payload(record))


def _build_logged_payload(record):
    message = record.getMessage()
    etype = "LoggedCritical" if record.levelno >= logging.CRITICAL else "LoggedError"
    payload = {
        "type": etype,
        "message": message,
        "traceback": [
            f"Logged {record.levelname} from logger '{record.name}':\n",
            f'  File "{record.pathname}", line {record.lineno}, in {record.funcName}\n',
            f"{etype}: {message}\n",
        ],
        "frames": [{
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName,
            "code": None,
        }],
    }
    if _server_name:
        payload["server_name"] = _server_name
    return payload


def _build_synthetic_payload(message, user=None):
    frames_obj = traceback.extract_stack()[:-2]  # drop trap() and this builder
    formatted = ["Traceback (most recent call last):\n"]
    formatted += traceback.format_list(frames_obj)
    formatted.append(f"TrappedEvent: {message}\n")
    payload = {
        "type": "TrappedEvent",
        "message": message,
        "traceback": formatted,
        "frames": [
            {"file": f.filename, "line": f.lineno, "function": f.name, "code": f.line}
            for f in frames_obj
        ],
    }
    if _server_name:
        payload["server_name"] = _server_name
    if user and _send_user:
        payload["user"] = user
    return payload


def _build_payload(exc_type, exc_value, exc_tb, user=None):
    frames = traceback.extract_tb(exc_tb) if exc_tb else []
    payload = {
        "type": exc_type.__name__,
        "message": str(exc_value),
        "traceback": traceback.format_exception(exc_type, exc_value, exc_tb) if exc_tb else [],
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
    if _server_name:
        payload["server_name"] = _server_name
    if user and _send_user:
        payload["user"] = user
    return payload


def _post(payload):
    try:
        if _channel == "adhoc":
            payload["channel"] = "adhoc"
        req = urllib.request.Request(
            _endpoint,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass
