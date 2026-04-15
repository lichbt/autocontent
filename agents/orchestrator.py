"""Orchestrator Agent: routes pipeline flow based on state and agent decisions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from agents.base import BaseAgent
from core.logging import get_logger
from core.models import (
    AgentDecisionStatus,
    AgentType,
    Cluster,
    ClusterStatus,
    JobQueue,
    JobType,
    JobStatus,
)

logger = get_logger("agents.orchestrator")


class OrchestratorAgent(BaseAgent):
    """Decides next pipeline action based on cluster/agent state."""

    agent_type = AgentType.ORCHESTRATOR

    def __init__(self, session: Session):
        super().__init__(session)

    def run(self) -> int:
        dispatched = 0

        pending_clusters = (
            self.session.query(Cluster)
            .filter(
                Cluster.status.in_([
                    ClusterStatus.PENDING_BRIEF,
                    ClusterStatus.BRIEF_GENERATED,
                    ClusterStatus.BRIEF_QC_PASSED,
                    ClusterStatus.PENDING_WRITE,
                    ClusterStatus.ARTICLE_DRAFTED,
                    ClusterStatus.ARTICLE_QC_PASSED,
                    ClusterStatus.PENDING_PUBLISH,
                    ClusterStatus.ARTICLE_QC_FAILED,
                ])
            )
            .all()
        )

        for cluster in pending_clusters:
            action = self._decide_action(cluster)
            if action:
                self._dispatch_job(cluster, action)
                dispatched += 1

        self.session.commit()
        return dispatched

    def _decide_action(self, cluster: Cluster) -> JobType | None:
        status = cluster.status
        if status == ClusterStatus.PENDING_BRIEF:
            return JobType.BRIEF
        if status in (ClusterStatus.BRIEF_GENERATED, ClusterStatus.BRIEF_QC_PASSED, ClusterStatus.PENDING_WRITE):
            return JobType.WRITE
        if status in (ClusterStatus.ARTICLE_DRAFTED, ClusterStatus.ARTICLE_QC_PASSED, ClusterStatus.PENDING_PUBLISH):
            return JobType.PUBLISH
        if status == ClusterStatus.ARTICLE_QC_FAILED:
            return JobType.WRITE
        return None

    def _dispatch_job(self, cluster: Cluster, job_type: JobType) -> None:
        existing = (
            self.session.query(JobQueue)
            .filter(
                JobQueue.cluster_id == cluster.id,
                JobQueue.job_type == job_type,
                JobQueue.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
            )
            .first()
        )
        if existing:
            logger.debug("Job already pending", extra_data={"cluster_id": cluster.id, "job_type": job_type.value})
            return

        job = JobQueue(
            site_id=cluster.site_id,
            cluster_id=cluster.id,
            job_type=job_type,
            status=JobStatus.PENDING,
            priority=self._priority(job_type),
            scheduled_at=datetime.now(timezone.utc),
        )
        self.session.add(job)
        self.session.flush()

        logger.info("Job dispatched", extra_data={"cluster_id": cluster.id, "job_type": job_type.value, "job_id": job.id})
        self.record_decision(
            decision_status=AgentDecisionStatus.PASS,
            site_id=cluster.site_id,
            cluster_id=cluster.id,
            event_data={"action": "dispatch_job", "job_type": job_type.value},
            recommended_action=f"run_{job_type.value}",
        )

    @staticmethod
    def _priority(job_type: JobType) -> int:
        return {
            JobType.INTAKE: 100,
            JobType.CLUSTER: 90,
            JobType.BRIEF: 80,
            JobType.QC_BRIEF: 70,
            JobType.WRITE: 60,
            JobType.QC_ARTICLE: 50,
            JobType.PUBLISH: 40,
        }.get(job_type, 50)