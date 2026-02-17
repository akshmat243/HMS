from collections import defaultdict

_EVENT_HANDLERS = defaultdict(list)

def event_handler(event_cls):
    def decorator(func):
        _EVENT_HANDLERS[event_cls].append(func)
        return func
    return decorator

class BaseEvent:
    def emit(self):
        for handler in _EVENT_HANDLERS[self.__class__]:
            handler(self)
