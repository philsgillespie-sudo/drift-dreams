"""Publish/subscribe, so systems react to each other without holding references to each other.

Events are plain objects (dataclasses); handlers subscribe to an event's class.
"""
from collections import defaultdict


class EventBus:
    def __init__(self):
        self._handlers = defaultdict(list)

    def subscribe(self, event_type, handler):
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type, handler):
        self._handlers[event_type].remove(handler)

    def publish(self, event):
        for handler in self._handlers.get(type(event), ()):
            handler(event)
