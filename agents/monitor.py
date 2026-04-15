"""Monitor Agent: operational health checks and notification dispatch."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from sqlalchemy.orm import Session

from agents.base import BaseAgent
from core.logging import get_logger
from core.models import (
    AgentDecisionStatus,
    AgentType,
    Cluster,
    ClusterStatus,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    JobQueue,
    JobStatus,
    Notification,
    NotificationChannel,
    NotificationDeliveryStatus,
    Site,
)

logger = get_logger("agents.monitor")


class MonitorAgent:
    """Observes pipeline health, tracks stuck jobs, detects incident patterns."""

    agent_type = AgentType.MONITOR
    STUCK_THRESHOLD_MINUTES = 120
    HIGH_INCIDENT_THRESHOLD = 5

    def __init__(self, session: Session, telegram_bot_token: Optional[str] = None, telegram_chat_id: Optional[str] = None):
        self.session = session
        self.telegram_bot_token = telegram_bot_token
        self.telegram_chat_id = telegram_chat_id

    def run(self) -> dict[str, Any]:
        report: dict[str, Any] = {}

        stuck = self._check_stuck_jobs()
        report["stuck_jobs"] = stuck

        new_incidents = self._detect_incident_patterns()
        report["new_incidents"] = new_incidents

        alerts = self._dispatch_alerts(report)
        report["alerts_sent"] = alerts

        return report

    def _check_stuck_jobs(self) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=self.STUCK_THRESHOLD_MINUTES)
        stuck = (
            self.session.query(JobQueue)
            .filter(
                JobQueue.status == JobStatus.RUNNING,
                JobQueue.started_at < cutoff,
            )
            .all()
        )
        if not stuck:
            return 0

        for job in stuck:
            incident = Incident(
                id=str(uuid.uuid4()),
                site_id=job.site_id,
                job_id=job.id,
                incident_type="JOB_STUCK",
                severity=IncidentSeverity.MEDIUM,
                root_cause=f"Job {job.job_type.value} stuck for over {self.STUCK_THRESHOLD_MINUTES} minutes",
                details_json={"job_type": job.job_type.value, "started_at": job.started_at.isoformat() if job.started_at else None},
            )
            self.session.add(incident)
            job.status = JobStatus.MANUAL_REVIEW

        self.session.commit()
        logger.warning("Stuck jobs detected and escalated", extra_data={"count": len(stuck)})
        return len(stuck)

    def _detect_incident_patterns(self) -> int:
        recent = datetime.now(timezone.utc) - timedelta(hours=4)
        sites_with_issues = (
            self.session.query(Incident.site_id, Incident.incident_type)
            .filter(Incident.created_at > recent, Incident.status == IncidentStatus.OPEN)
            .distinct()
            .all()
        )
        created = 0
        seen: set[tuple[str, str]] = set()
        for site_id, incident_type in sites_with_issues:
            count = (
                self.session.query(Incident)
                .filter(
                    Incident.site_id == site_id,
                    Incident.incident_type == incident_type,
                    Incident.created_at > recent,
                    Incident.status == IncidentStatus.OPEN,
                )
                .count()
            )
            if count >= self.HIGH_INCIDENT_THRESHOLD and (site_id, incident_type) not in seen:
                seen.add((site_id, incident_type))
                existing = (
                    self.session.query(Incident)
                    .filter(
                        Incident.site_id == site_id,
                        Incident.incident_type == f"HIGH_VOLUME_{incident_type}",
                        Incident.status == IncidentStatus.OPEN,
                    )
                    .first()
                )
                if not existing:
                    incident = Incident(
                        id=str(uuid.uuid4()),
                        site_id=site_id,
                        incident_type=f"HIGH_VOLUME_{incident_type}",
                        severity=IncidentSeverity.HIGH,
                        root_cause=f"Site {site_id} has {count} incidents of type {incident_type} in the last 4 hours",
                    )
                    self.session.add(incident)
                    created += 1

        self.session.commit()
        return created

    def _dispatch_alerts(self, report: dict[str, Any]) -> int:
        urgent_incidents = (
            self.session.query(Incident)
            .filter(
                Incident.severity.in_([IncidentSeverity.HIGH, IncidentSeverity.CRITICAL]),
                Incident.status == IncidentStatus.OPEN,
            )
            .all()
        )
        if not urgent_incidents:
            return 0

        message = self._format_telegram_alert(urgent_incidents, report)
        sent = self._send_telegram(message)
        if sent:
            for inc in urgent_incidents:
                notification = Notification(
                    id=str(uuid.uuid4()),
                    incident_id=inc.id,
                    channel=NotificationChannel.TELEGRAM,
                    recipient=self.telegram_chat_id or "unknown",
                    message=message,
                    sent_at=datetime.now(timezone.utc),
                    delivery_status=NotificationDeliveryStatus.SENT,
                )
                self.session.add(notification)
            self.session.commit()
            logger.info("High-urgency Telegram alert sent", extra_data={"count": len(urgent_incidents)})
        return len(urgent_incidents)

    @staticmethod
    def _format_telegram_alert(incidents: list[Incident], report: dict[str, Any]) -> str:
        lines = ["🚨 SEO Content Engine Alert", ""]
        for inc in incidents[:5]:
            lines.append(f"• [{inc.severity.value.upper()}] {inc.incident_type}")
            if inc.root_cause:
                lines.append(f"  {inc.root_cause[:100]}")
        if report.get("stuck_jobs"):
            lines.append(f"\n⚠️ Stuck jobs: {report['stuck_jobs']}")
        if report.get("new_incidents"):
            lines.append(f"📊 New incident patterns: {report['new_incidents']}")
        lines.append("\n🔗 Check logs/ for details.")
        return "\n".join(lines)

    def _send_telegram(self, message: str) -> bool:
        if not self.telegram_bot_token or not self.telegram_chat_id:
            logger.info("Telegram credentials not configured, skipping alert")
            return False
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                json={"chat_id": self.telegram_chat_id, "text": message, "parse_mode": "HTML"},
                timeout=15,
            )
            return response.status_code == 200
        except Exception as exc:
            logger.error("Telegram send failed", extra_data={"error": str(exc)})
            return False