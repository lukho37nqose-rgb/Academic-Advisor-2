"""
Event Dispatcher.

Enterprise software emits events. This allows external systems (webhooks, metrics, 
billing, or asynchronous background jobs) to subscribe to the reasoning engine's 
lifecycle without tightly coupling the code.
"""

from typing import Dict, Any, Callable, List
import asyncio
import json
from .telemetry import Telemetry

class EventDispatcher:
    """A lightweight async Pub/Sub dispatcher."""
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, handler: Callable):
        """Registers a callback for a specific event."""
        if event_name not in self._subscribers:
            self._subscribers[event_name] = []
        self._subscribers[event_name].append(handler)

    async def emit(self, event_name: str, payload: Dict[str, Any]):
        """
        Emits an event to all registered subscribers asynchronously.
        Also automatically logs the event to the telemetry system.
        """
        # Always log the event for observability
        Telemetry.log_event(event_name, **payload)
        
        if event_name in self._subscribers:
            # Fire and forget handlers
            tasks = [asyncio.create_task(handler(payload)) for handler in self._subscribers[event_name]]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

# Global instance for the application
dispatcher = EventDispatcher()


# No default subscribers are registered. In-process event handlers are useful
# for local observability only; they are not a delivery guarantee and may not
# call an institutional system of record.
