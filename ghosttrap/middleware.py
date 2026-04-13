"""Django middleware for automatic error reporting.

Add to MIDDLEWARE in your Django settings:

    MIDDLEWARE = [
        ...
        "ghosttrap.middleware.GhostTrapMiddleware",
    ]
"""

from ghosttrap.client import report


class GhostTrapMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        report(exception)
        return None
