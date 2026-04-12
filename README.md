# ghosttrap-sdk

Drop-in error reporter for Python apps.

## Install

```
pip install ghosttrap-sdk
```

## Use

```python
import ghosttrap

# with a token (get one from `ghosttrap watch`):
ghosttrap.init("t_abc123def456")

# or with a full URL:
ghosttrap.init("https://ghosttrap.io/trap/owner/repo/")
```

Unhandled exceptions are POSTed to ghosttrap.io with full tracebacks.
The original `sys.excepthook` is preserved so errors still print to
stderr as normal.

For caught exceptions inside web frameworks:

```python
try:
    do_something()
except Exception as exc:
    ghosttrap.report(exc)
    raise
```
