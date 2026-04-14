# ghosttrap-sdk

Error reporting for Python apps, built for AI agents. Part of [ghosttrap](https://github.com/arowley-predictive-power/ghosttrap-cli).

## Install

```
pip install ghosttrap-sdk
```

## Use

```python
import ghosttrap
ghosttrap.init("t_your_token_here")
```

Get your token by running `ghosttrap setup` from [ghosttrap-cli](https://github.com/arowley-predictive-power/ghosttrap-cli).

## What it hooks into

- **`sys.excepthook`** — unhandled exceptions
- **Python logging** — `logger.exception()` and `logger.error(..., exc_info=True)`
- **Celery** — task failures via `celery.signals.task_failure` (auto-detected)

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

## Zero dependencies

Pure Python stdlib. No transitive dependencies in your production image.
