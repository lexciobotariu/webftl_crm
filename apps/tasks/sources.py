"""Where a change to a task came from: the app's own screens, or Claude through the MCP endpoint.

The MCP endpoint wraps each call in ``acting_via(CLAUDE)``; activity rows and
time entries made meanwhile take that value as their ``source`` default, so
every service keeps working unchanged and the drawer can say "via Claude".
"""
import contextvars
from contextlib import contextmanager

SCREENS = ''
CLAUDE = 'claude'
CHOICES = [(SCREENS, 'App'), (CLAUDE, 'Claude')]

_current = contextvars.ContextVar('task_change_source', default=SCREENS)


def current():
    return _current.get()


@contextmanager
def acting_via(source):
    token = _current.set(source)
    try:
        yield
    finally:
        _current.reset(token)
