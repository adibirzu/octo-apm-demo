"""Realistic synthetic traffic generator for octo-apm-demo.

Emits HTTP requests + OTel traces that look like a real user population
so APM, RUM, and Log Analytics have something to observe.
"""

from .config import TrafficConfig
from .population import Population
from .session import Session, SessionOutcome

__all__ = ["TrafficConfig", "Population", "Session", "SessionOutcome"]
__version__ = "1.0.0"
