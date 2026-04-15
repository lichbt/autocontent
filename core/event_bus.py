"""
Simple in-process event bus for the SEO Content Engine.
Provides publish-subscribe semantics for pipeline and agent communication.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.logging import get_logger

logger = get_logger("core.event_bus")


@dataclass
class Event:
    """A domain event emitted by modules or agents."""

    event_type: str
    source: str
    site_id: Optional[str] = None
    cluster_id: Optional[str] = None
    article_id: Optional[str] = None
    job_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "source": self.source,
            "site_id": self.site_id,
            "cluster_id": self.cluster_id,
            "article_id": self.article_id,
            "job_id": self.job_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
        }


# Global registry of handlers per event type
_HANDLERS: Dict[str, List[Callable[[Event], None]]] = {}


def subscribe(event_type: str, handler: Callable[[Event], None]) -> None:
    """Register a handler for a specific event type."""
    if event_type not in _HANDLERS:
        _HANDLERS[event_type] = []
    if handler not in _HANDLERS[event_type]:
        _HANDLERS[event_type].append(handler)
        logger.debug(f"Subscribed handler to event: {event_type}")


def unsubscribe(event_type: str, handler: Callable[[Event], None]) -> None:
    """Unregister a handler."""
    if event_type in _HANDLERS and handler in _HANDLERS[event_type]:
        _HANDLERS[event_type].remove(handler)


def emit(event_type: str, source: str, **kwargs: Any) -> Event:
    """Emit an event and notify all registered handlers."""
    event = Event(event_type=event_type, source=source, **kwargs)
    logger.info(f"Event emitted: {event_type}", extra_data={"event": event.to_dict()})
    handlers = _HANDLERS.get(event_type, [])
    for handler in handlers:
        try:
            handler(event)
        except Exception as exc:
            logger.error(
                f"Event handler failed for {event_type}",
                extra_data={"handler": handler.__name__, "error": str(exc)},
            )
    return event


# Built-in event type constants
class Events:
    # Intake
    KEYWORD_INGESTED = "keyword.ingested"

    # Clustering
    CLUSTER_CREATED = "cluster.created"

    # Briefing
    BRIEF_GENERATED = "brief.generated"
    BRIEF_FAILED = "brief.failed"

    # Writing
    ARTICLE_GENERATED = "article.generated"
    ARTICLE_GENERATION_FAILED = "article.generation_failed"

    # QC
    QC_PASSED = "qc.passed"
    QC_FAILED = "qc.failed"

    # Publishing
    PUBLISH_SUCCEEDED = "publish.succeeded"
    PUBLISH_FAILED = "publish.failed"

    # Job lifecycle
    JOB_STUCK = "job.stuck"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"
    JOB_RETRY = "job.retry"

    # Agents
    AGENT_ESCALATION = "agent.escalation"
    AGENT_DECISION = "agent.decision"

    # Pipeline
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    PIPELINE_SUMMARY = "pipeline.summary"