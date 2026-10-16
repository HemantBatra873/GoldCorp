"""
GoldCorp trading domain.

Pure Python — must not import Django models, views, or settings.
Callable from management commands, Celery workers, and APIs.
"""

from trading.types import ENGINE_VERSION

__version__ = "0.2.0"
__all__ = ["ENGINE_VERSION", "__version__"]
