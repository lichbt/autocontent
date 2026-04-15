"""Recovery Agent: handles failures with retry or escalation logic."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from agents.base import BaseAgent
from core.logging import get_logger
from core.models import (
    AgentDecisionStatus,
    AgentType,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    JobQueue,
    JobStatus,
)

logger = get_logger("agents.recovery")


class RecoveryAgent(BaseAgent):
    """Diagnose failures with retry or escalation logic."""

    agent_type = AgentType.RECOVERY

    RETRY_DELAYS = [60, 300, 900]  # seconds: 1m, 5m, 15m

    def __init__(self, session: Session):
        super().__init__(session)

    def run(self) -> int:
        recovered = 0
        for job in self.session.query(JobQueue).filter(
            JobQueue.status.in_([JobStatus.FAILED, JobStatus.RETRY])
        ).all():
            if job.attempt_count < job.max_attempts:
                self._retry_job(job)
                recovered += 1
            else:
                self._escalate(job)
                recovered += 1
        self.session.commit()
        return recovered

    def _retry_job(self, job: JobQueue) -> None:
        job.attempt_count += 1
        job.status = JobStatus.PENDING
        job.error_code = None
        job.error_message = None
        delay = self.RETRY_DELAYS[min(job.attempt_count - 1, len(self.RETRY_DELAYS) - 1)]
        job.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay)

        self.record_decision(
            decision_status=AgentDecisionStatus.RETRY,
            job_id=job.id,
            site_id=job.site_id,
            cluster_id=job.cluster_id,
            event_data={"attempt": job.attempt_count, "max": job.max_attempts},
            reason_json={"retry_delay": delay, "error_code": job.error_code},
            recommended_action="retry",
        )
        logger.info("Job scheduled for retry", extra_data={"job_id": job.id, "attempt": job.attempt_count})

    def _escalate(self, job: JobQueue) -> None:
        job.status = JobStatus.MANUAL_REVIEW
        incident_type = self._classify(job.error_code or "")
        severity = self._severity(incident_type)

        incident = Incident(
            incident_type=incident_type,
            site_id=job.site_id,
            cluster_id=job.cluster_id,
            article_id=job.article_id,
            job_id=job.id,
            severity=severity,
            root_cause=str(job.error_message or "Max retries exceeded"),
            details_json={"error_code": job.error_code, "error_message": job.error_message, "attempts": job.attempt_count},
        )
        self.session.add(incident)

        self.record_decision(
            decision_status=AgentDecisionStatus.ESCALATE,
            job_id=job.id,
            site_id=job.site_id,
            cluster_id=job.cluster_id,
            article_id=job.article_id,
            event_data={"incident_type": incident_type},
            reason_json={"max_attempts_reached": True},
            recommended_action="manual_review",
        )
        logger.warning(
            "Job escalated to manual review",
            extra_data={"job_id": job.id, "incident_type": incident_type, "severity": severity.value},
        )

    @staticmethod
    def _classify(error_code: str) -> str:
        code = error_code.lower()
        if "timeout" in code or "timed out" in code:
            return "TIMEOUT"
        if "429" in code or "rate limit" in code:
            return "RATE_LIMIT"
        if "blocked" in code or "captcha" in code or "cloudflare" in code:
            return "SCRAPE_BLOCKED"
        if "json" in code or "parse" in code:
            return "INVALID_JSON"
        if "401" in code or "403" in code or "auth" in code:
            return "AUTH_EXPIRED"
        if "schema" in code:
            return "SCHEMA_REJECT"
        return "UNKNOWN_FAILURE"

    @staticmethod
    def _severity(incident_type: str) -> IncidentSeverity:
        return {
            "TIMEOUT": IncidentSeverity.LOW,
            "RATE_LIMIT": IncidentSeverity.MEDIUM,
            "SCRAPE_BLOCKED": IncidentSeverity.MEDIUM,
            "INVALID_JSON": IncidentSeverity.LOW,
            "AUTH_EXPIRED": IncidentSeverity.HIGH,
            "SCHEMA_REJECT": IncidentSeverity.MEDIUM,
            "UNKNOWN_FAILURE": IncidentSeverity.HIGH,
        }.get(incident_type, IncidentSeverity.MEDIUM)