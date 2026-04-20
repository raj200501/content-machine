"""Compatibility wrapper for tenacity."""

from __future__ import annotations

try:  # pragma: no cover - exercised implicitly when tenacity is installed.
    from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
except Exception:  # pragma: no cover - fallback used in dependency-light environments.
    def retry(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    def retry_if_exception_type(*args, **kwargs):
        return None

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None
