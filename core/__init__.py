"""
Core module for SEO Content Engine.
Exposes the main database session and all models for easy imports.
"""

from core.db import get_session, init_db, engine, Session
from core.models import (
    Base,
    Site,
    Keyword,
    Cluster,
    Article,
    PipelineRun,
    JobQueue,
    AgentDecision,
    Incident,
    Notification,
    Artifact,
    # Enums
    CMSChoice,
    KeywordStatus,
    ClusterStatus,
    ArticleStatus,
    PipelineRunStatus,
    JobType,
    JobStatus,
    AgentType,
    AgentDecisionStatus,
    IncidentSeverity,
    IncidentStatus,
    NotificationChannel,
    NotificationDeliveryStatus,
    SearchIntent,
    ArtifactType,
)

__all__ = [
    # DB
    "get_session",
    "init_db",
    "engine",
    "Session",
    "Base",
    # Models
    "Site",
    "Keyword",
    "Cluster",
    "Article",
    "PipelineRun",
    "JobQueue",
    "AgentDecision",
    "Incident",
    "Notification",
    "Artifact",
    # Enums
    "CMSChoice",
    "KeywordStatus",
    "ClusterStatus",
    "ArticleStatus",
    "PipelineRunStatus",
    "JobType",
    "JobStatus",
    "AgentType",
    "AgentDecisionStatus",
    "IncidentSeverity",
    "IncidentStatus",
    "NotificationChannel",
    "NotificationDeliveryStatus",
    "SearchIntent",
    "ArtifactType",
]