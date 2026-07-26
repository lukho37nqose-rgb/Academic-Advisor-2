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


# --- Mock Handlers for Demonstration ---

async def on_evaluation_completed(payload: Dict[str, Any]):
    """Example subscriber that might trigger Webhooks or external Workflow execution."""
    print(f"\n[EVENT DISPATCHER] Triggered Webhook for evaluation completion: {payload.get('evaluation_id')}")

# Register default system handlers
dispatcher.subscribe("evaluation.completed", on_evaluation_completed)
