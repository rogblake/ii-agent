"""Celery integration for ii_agent."""

from ii_agent.workers.celery.app import celery_app

__all__ = ["celery_app"]
