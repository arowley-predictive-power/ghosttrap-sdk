# ghosttrap-sdk

Error reporting for Python apps, built for AI agents. Part of [ghosttrap](https://github.com/alex-rowley/ghosttrap-cli).

## Install

```
pip install ghosttrap-sdk
```

## Use

```python
import ghosttrap
ghosttrap.init("t_your_token_here")
```

Get your token by running `ghosttrap setup` from [ghosttrap-cli](https://github.com/alex-rowley/ghosttrap-cli).

### Optional kwargs

```python
ghosttrap.init(
    "t_your_token_here",
    server="https://ghosttrap.io",  # override only if self-hosting
    send_user=False,                # see "User context" below
    trap_logs=False,                # see "Bare log errors" below
)
```

## What it hooks into

- **`sys.excepthook`** — unhandled exceptions
- **`threading.excepthook`** — unhandled exceptions in background threads (these never reach `sys.excepthook`)
- **Python logging** — `logger.exception()` and `logger.error(..., exc_info=True)`
- **Celery** — task failures via `celery.signals.task_failure` (auto-detected)

## Bare log errors (opt-in)

By default, only log records carrying an exception are reported. Pass `trap_logs=True` to also report `logger.error()` / `logger.critical()` calls with no exception — they arrive as type `LoggedError` / `LoggedCritical` with the log call site as the frame. Off by default deliberately: in a chatty codebase every error-level log line becomes an event, and error trackers that default this on are famous for the resulting floods. The server's 5-minute dedup window still applies either way.

## What it sends

Every report includes the exception type, message, traceback, frames (file/line/function/code), and the server's hostname (`socket.gethostname()`).

## Ad-hoc shell errors (shelved, never streamed)

Errors only stream if the crashing code lives in the repo. Code someone typed — `manage.py shell` / `shell_plus`, `python -c`, piped stdin, a REPL — has no file, no line, no commit, and its author already watched it fail in their own terminal. The SDK detects these processes at `init()` and tags their reports `channel: adhoc`; the server stores them on the same quarantined shelf as browser events (capped, deduped, pull-only via `ghosttrap shelf`) instead of waking the repo's agent. Service processes — web workers, celery, real management commands like `migrate` — stream normally.

Overrides: `GHOSTTRAP_CHANNEL=service` or `GHOSTTRAP_CHANNEL=adhoc` forces the channel; `GHOSTTRAP_DISABLE=1` makes `init()` a no-op for that process.

## Django

```python
INSTALLED_APPS = [
    ...
    "ghosttrap.django.GhostTrapApp",
]

MIDDLEWARE = [
    "ghosttrap.django.GhostTrapMiddleware",
    ...
]
```

## Browser / JavaScript errors (quarantined)

Browser errors are captured but **never stream**. A browser can't hold a secret, so its events are anonymous — and ghosttrap streams carry agent-to-agent messages that agents act on. Rather than let anonymous text into that channel, browser events go to a quarantined shelf: stored server-side, capped and deduped, never fanned out to `peek`/`watch`, never touching the cursor. Retrieval is pull-only via `ghosttrap shelf` (from ghosttrap-cli), which labels them as untrusted telemetry.

Wiring is the same two lines as before:

```python
# urls.py
path("ghosttrap/", include("ghosttrap.django.urls")),
```

```html
<!-- base template -->
<script src="{% static 'ghosttrap/ghosttrap.js' %}" defer></script>
```

The script hooks uncaught errors and unhandled promise rejections, drops known junk (opaque cross-origin `"Script error."`, browser-extension noise), dedupes per page, and caps itself at 10 reports per page load. The relay forwards to the server's `/trapjs/` ingest using your `init()` config — no token in page source, no CORS, no third-party request for ad blockers to eat. Server-side: 5-minute dedup and a 500-event per-repo retention cap.

## Manually trap an event

For errors you catch and handle but still want logged, or for non-exception conditions worth flagging:

```python
import ghosttrap

try:
    do_thing()
except ValueError as e:
    ghosttrap.trap(e)        # caught exception — sent with type, message, traceback
    fallback()

ghosttrap.trap("payment gateway returned 503")  # synthetic event labelled "TrappedEvent"
```

`trap()` accepts an exception instance or a string. Strings get the caller's stack attached and a `TrappedEvent` type so they're distinct from real exceptions in the CLI. Both go through the same 5-minute dedup window as the auto-hook.

## User context

Off by default. Pass `send_user=True` to `init()` and the Django middleware will attach the authenticated user's `id` and `username` to each report. Has no effect outside Django.

```python
ghosttrap.init("t_your_token_here", send_user=True)
```

## Zero dependencies

Pure Python stdlib. No transitive dependencies in your production image.
