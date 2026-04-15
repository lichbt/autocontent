"""Base agent class with decision logging."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from core.logging import get_logger
from core.models import AgentDecision, AgentDecisionStatus, AgentType

logger = get_logger("agents.base")


class BaseAgent:
    """Base class for all agents providing common decision logging and DB access."""

    agent_type: AgentType

    def __init__(self, session: Session):
        self.session = session
        if not hasattr(self, "agent_type"):
            raise ValueError("Agent subclasses must define agent_type")

    def record_decision(
        self,
        decision_status: AgentDecisionStatus,
        *,
        job_id: Optional[str] = None,
        site_id: Optional[str] = None,
        cluster_id: Optional[str] = None,
        article_id: Optional[str] = None,
        event_data: Optional[dict[str, Any]] = None,
        score: Optional[float] = None,
        reason_json: Optional[dict[str, Any]] = None,
        recommended_action: Optional[str] = None,
    ) -> AgentDecision:
        decision = AgentDecision(
            agent_type=self.agent_type,
            job_id=job_id,
            site_id=site_id,
            cluster_id=cluster_id,
            article_id=article_id,
            event_data=event_data,
            decision_status=decision_status,
            score=score,
            reason_json=reason_json,
            recommended_action=recommended_action,
        )
        self.session.add(decision)
        self.session.flush()
        logger.info(
            "Agent decision recorded",
            extra_data={
                "agent": self.agent_type.value,
                "status": decision_status.value,
                "score": score,
                "decision_id": decision.id,
            },
        )
        return decision