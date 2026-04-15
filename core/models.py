"""SQLAlchemy models for the SEO Content Engine."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


# -------------------------
# Enum definitions
# -------------------------


class CMSChoice(str, enum.Enum):
    WORDPRESS = "wordpress"


class SearchIntent(str, enum.Enum):
    INFORMATIONAL = "informational"
    COMMERCIAL = "commercial"
    TRANSACTIONAL = "transactional"
    BRANDED = "branded"
    LOCAL = "local"


class KeywordStatus(str, enum.Enum):
    PENDING_INTAKE = "pending_intake"
    PENDING_CLUSTER = "pending_cluster"
    CLUSTERED = "clustered"


class ClusterStatus(str, enum.Enum):
    PENDING_BRIEF = "pending_brief"
    BRIEF_GENERATED = "brief_generated"
    BRIEF_QC_PASSED = "brief_qc_passed"
    BRIEF_QC_FAILED = "brief_qc_failed"
    PENDING_WRITE = "pending_write"
    ARTICLE_DRAFTED = "article_drafted"
    ARTICLE_QC_PASSED = "article_qc_passed"
    ARTICLE_QC_FAILED = "article_qc_failed"
    PENDING_PUBLISH = "pending_publish"
    PUBLISHED = "published"
    ERROR = "error"
    MANUAL_REVIEW = "manual_review"


class ArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"
    ERROR = "error"


class PipelineRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL_SUCCESS = "partial_success"


class JobType(str, enum.Enum):
    INTAKE = "intake"
    CLUSTER = "cluster"
    BRIEF = "brief"
    WRITE = "write"
    QC_BRIEF = "qc_brief"
    QC_ARTICLE = "qc_article"
    PUBLISH = "publish"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    MANUAL_REVIEW = "manual_review"
    HALTED = "halted"


class AgentType(str, enum.Enum):
    ORCHESTRATOR = "orchestrator"
    QC = "qc"
    RECOVERY = "recovery"
    MONITOR = "monitor"


class AgentDecisionStatus(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    RETRY = "retry"
    ESCALATE = "escalate"
    HALT = "halt"
    PASS_WITH_WARNING = "pass_with_warning"


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class NotificationChannel(str, enum.Enum):
    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"


class NotificationDeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ArtifactType(str, enum.Enum):
    KEYWORD_SET = "keyword_set"
    BRIEF_JSON = "brief_json"
    OUTLINE_JSON = "outline_json"
    ARTICLE_MD = "article_md"
    ARTICLE_HTML = "article_html"
    SCHEMA_JSON = "schema_json"


# -------------------------
# Shared base entity
# -------------------------


class BaseEntity(Base):
    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# -------------------------
# Models
# -------------------------


class Site(BaseEntity):
    __tablename__ = "sites"

    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    cms_type: Mapped[CMSChoice] = mapped_column(SQLEnum(CMSChoice), nullable=False, default=CMSChoice.WORDPRESS)
    cms_api_config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)
    config_yaml: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True, default=dict)

    keywords: Mapped[list["Keyword"]] = relationship("Keyword", back_populates="site", cascade="all, delete-orphan")
    clusters: Mapped[list["Cluster"]] = relationship("Cluster", back_populates="site", cascade="all, delete-orphan")
    runs: Mapped[list["PipelineRun"]] = relationship("PipelineRun", back_populates="site", cascade="all, delete-orphan")


class Keyword(BaseEntity):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("site_id", "raw_keyword", name="uq_keywords_site_raw_keyword"),
        Index("ix_keywords_site_status", "site_id", "status"),
    )

    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    raw_keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    search_volume: Mapped[Optional[int]] = mapped_column(nullable=True)
    difficulty: Mapped[Optional[int]] = mapped_column(nullable=True)
    intent: Mapped[Optional[SearchIntent]] = mapped_column(SQLEnum(SearchIntent), nullable=True)
    status: Mapped[KeywordStatus] = mapped_column(SQLEnum(KeywordStatus), nullable=False, default=KeywordStatus.PENDING_INTAKE)

    site: Mapped[Site] = relationship("Site", back_populates="keywords")


class Cluster(BaseEntity):
    __tablename__ = "clusters"
    __table_args__ = (
        Index("ix_clusters_site_status", "site_id", "status"),
        Index("ix_clusters_primary_keyword_id", "primary_keyword_id"),
    )

    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    primary_keyword_id: Mapped[str] = mapped_column(String(36), ForeignKey("keywords.id", ondelete="CASCADE"), nullable=False)
    secondary_keyword_ids: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True, default=list)
    search_intent: Mapped[SearchIntent] = mapped_column(SQLEnum(SearchIntent), nullable=False)
    status: Mapped[ClusterStatus] = mapped_column(SQLEnum(ClusterStatus), nullable=False, default=ClusterStatus.PENDING_BRIEF)
    brief_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    site: Mapped[Site] = relationship("Site", back_populates="clusters")
    primary_keyword: Mapped[Keyword] = relationship("Keyword", foreign_keys=[primary_keyword_id])
    article: Mapped[Optional["Article"]] = relationship("Article", back_populates="cluster", uselist=False, cascade="all, delete-orphan")


class Article(BaseEntity):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_status", "status"),
    )

    cluster_id: Mapped[str] = mapped_column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=False, unique=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    slug: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, unique=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    published_url: Mapped[Optional[str]] = mapped_column(String(511), nullable=True, unique=True)
    status: Mapped[ArticleStatus] = mapped_column(SQLEnum(ArticleStatus), nullable=False, default=ArticleStatus.DRAFT)

    cluster: Mapped[Cluster] = relationship("Cluster", back_populates="article")


class PipelineRun(BaseEntity):
    __tablename__ = "pipeline_runs"
    __table_args__ = (Index("ix_pipeline_runs_site_status", "site_id", "status"),)

    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[PipelineRunStatus] = mapped_column(SQLEnum(PipelineRunStatus), nullable=False, default=PipelineRunStatus.RUNNING)
    total_clusters: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)
    fail_count: Mapped[int] = mapped_column(default=0)

    site: Mapped[Site] = relationship("Site", back_populates="runs")


class JobQueue(BaseEntity):
    __tablename__ = "job_queue"
    __table_args__ = (
        Index("ix_job_queue_status_priority", "status", "priority"),
        Index("ix_job_queue_scheduled_at", "scheduled_at"),
    )

    run_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clusters.id", ondelete="CASCADE"), nullable=True)
    article_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("articles.id", ondelete="CASCADE"), nullable=True)
    job_type: Mapped[JobType] = mapped_column(SQLEnum(JobType), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING)
    priority: Mapped[int] = mapped_column(default=0)
    attempt_count: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)


class AgentDecision(BaseEntity):
    __tablename__ = "agent_decisions"
    __table_args__ = (Index("ix_agent_decisions_agent_created", "agent_type", "created_at"),)

    job_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("job_queue.id", ondelete="SET NULL"), nullable=True)
    site_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)
    article_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    agent_type: Mapped[AgentType] = mapped_column(SQLEnum(AgentType), nullable=False)
    event_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    decision_status: Mapped[AgentDecisionStatus] = mapped_column(SQLEnum(AgentDecisionStatus), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(nullable=True)
    reason_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    recommended_action: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


class Incident(BaseEntity):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_site_created", "site_id", "created_at"),
    )

    site_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)
    article_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("job_queue.id", ondelete="SET NULL"), nullable=True)
    incident_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(SQLEnum(IncidentSeverity), nullable=False)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    occurrence_count: Mapped[int] = mapped_column(default=1)
    status: Mapped[IncidentStatus] = mapped_column(SQLEnum(IncidentStatus), nullable=False, default=IncidentStatus.OPEN)
    resolution_action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Notification(BaseEntity):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_channel_sent", "channel", "sent_at"),)

    incident_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("job_queue.id", ondelete="SET NULL"), nullable=True)
    channel: Mapped[NotificationChannel] = mapped_column(SQLEnum(NotificationChannel), nullable=False)
    recipient: Mapped[str] = mapped_column(String(512), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        SQLEnum(NotificationDeliveryStatus),
        nullable=False,
        default=NotificationDeliveryStatus.PENDING,
    )


class Artifact(BaseEntity):
    __tablename__ = "artifacts"
    __table_args__ = (
        Index("ix_artifacts_cluster_article", "cluster_id", "article_id"),
        Index("ix_artifacts_type_version", "artifact_type", "version"),
    )

    site_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    cluster_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clusters.id", ondelete="SET NULL"), nullable=True)
    article_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True)
    artifact_type: Mapped[ArtifactType] = mapped_column(SQLEnum(ArtifactType), nullable=False)
    version: Mapped[int] = mapped_column(default=1)
    content_path: Mapped[Optional[str]] = mapped_column(String(511), nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    content_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
