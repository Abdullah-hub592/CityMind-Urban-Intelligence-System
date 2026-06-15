"""Singleton publish/subscribe event bus for CityMind."""
from collections import defaultdict
from threading import RLock

# Event type constants
ROAD_BLOCKED = "ROAD_BLOCKED"
ROAD_UNBLOCKED = "ROAD_UNBLOCKED"
RISK_UPDATED = "RISK_UPDATED"
AMBULANCE_MOVED = "AMBULANCE_MOVED"
POLICE_MOVED = "POLICE_MOVED"
CIVILIAN_RESCUED = "CIVILIAN_RESCUED"
SIMULATION_STEP = "SIMULATION_STEP"
REROUTE = "REROUTE"


class EventBus:
    def __init__(self):
        self._subs = defaultdict(list)
        self._lock = RLock()

    def subscribe(self, event_type: str, callback):
        with self._lock:
            if callback not in self._subs[event_type]:
                self._subs[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback):
        with self._lock:
            if callback in self._subs[event_type]:
                self._subs[event_type].remove(callback)

    def publish(self, event_type: str, data: dict = None):
        data = data or {}
        with self._lock:
            callbacks = list(self._subs[event_type])
        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                print(f"[EventBus] Error in {event_type} subscriber: {e}")

    def clear(self):
        with self._lock:
            self._subs.clear()


bus = EventBus()
