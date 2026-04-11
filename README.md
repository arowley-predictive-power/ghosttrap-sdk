# ghosttrap-sdk

Drop-in error reporter for Python apps.

## Install

```
pip install ghosttrap-sdk
```

## Use

```python
import ghosttrap
ghosttrap.init("https://ghosttrap.io/trap/<your-token>")
```

Unhandled exceptions are POSTed to ghosttrap.io with full tracebacks.
The original `sys.excepthook` is preserved so errors still print to
stderr as normal.
