"""OCI Object Storage event pipeline.

Listens for Object Storage Events (com.oraclecloud.objectstorage.createobject)
via webhook, processes the object with a registered handler, emits an
outcome event (com.octodemo.object-pipeline.processed.*).
"""

from .api import create_app
from .handlers import HANDLERS, Handler, ProcessingResult

__all__ = ["create_app", "HANDLERS", "Handler", "ProcessingResult"]
__version__ = "1.0.0"
