"""QC Agent: quality-control scoring for briefs and articles."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from agents.base import BaseAgent
from core.logging import get_logger
from core.models import (
    AgentDecisionStatus,
    AgentType,
    Article,
    ArticleStatus,
    Cluster,
    ClusterStatus,
)

logger = get_logger("agents.qc")


class QCAgent(BaseAgent):
    """Quality control agent that scores briefs and articles against configurable thresholds."""

    agent_type = AgentType.QC

    def __init__(
        self,
        session: Session,
        *,
        brief_min_score: float = 0.80,
        article_min_score: float = 0.85,
        factual_fail_hard: bool = True,
    ):
        super().__init__(session)
        self.brief_min_score = brief_min_score
        self.article_min_score = article_min_score
        self.factual_fail_hard = factual_fail_hard

    def run(self) -> int:
        scored = 0
        for cluster in self.session.query(Cluster).filter(
            Cluster.status.in_([ClusterStatus.BRIEF_GENERATED, ClusterStatus.ARTICLE_DRAFTED])
        ).all():
            if cluster.status == ClusterStatus.BRIEF_GENERATED:
                self._check_brief(cluster)
            elif cluster.status == ClusterStatus.ARTICLE_DRAFTED:
                self._check_article(cluster)
            scored += 1
        self.session.commit()
        return scored

    def _check_brief(self, cluster: Cluster) -> None:
        brief = cluster.brief_json or {}
        issues: list[dict[str, Any]] = []
        score = 1.0

        if not brief.get("primary_keyword"):
            issues.append({"code": "MISSING_PRIMARY_KEYWORD", "severity": "high", "message": "Brief missing primary_keyword"})
            score -= 0.4

        if not brief.get("outline") or len(brief.get("outline", [])) < 2:
            issues.append({"code": "WEAK_OUTLINE", "severity": "medium", "message": "Outline has fewer than 2 sections"})
            score -= 0.2

        target_wc = brief.get("target_word_count") or 0
        if target_wc and (target_wc < 800 or target_wc > 5000):
            issues.append({"code": "UNREASONABLE_WORD_COUNT", "severity": "low", "message": f"Target word count {target_wc} is outside recommended range"})
            score -= 0.1

        verdict = self._verdict(score, self.brief_min_score)
        cluster.status = (
            ClusterStatus.BRIEF_QC_PASSED
            if verdict in (AgentDecisionStatus.PASS, AgentDecisionStatus.PASS_WITH_WARNING)
            else ClusterStatus.BRIEF_QC_FAILED
        )

        self.record_decision(
            decision_status=verdict,
            site_id=cluster.site_id,
            cluster_id=cluster.id,
            event_data={"event_type": "brief.check", "brief_keys": list(brief.keys())},
            score=score,
            reason_json={"issues": issues, "threshold": self.brief_min_score},
            recommended_action="proceed_to_write" if verdict in (AgentDecisionStatus.PASS, AgentDecisionStatus.PASS_WITH_WARNING) else "fix_brief",
        )

        logger.info(
            "Brief QC completed",
            extra_data={"cluster_id": cluster.id, "score": round(score, 3), "verdict": verdict.value, "issues": len(issues)},
        )

    def _check_article(self, cluster: Cluster) -> None:
        article = cluster.article
        if not article:
            cluster.status = ClusterStatus.ERROR
            return

        issues: list[dict[str, Any]] = []
        score = 1.0

        html = article.content_html or ""
        word_count = len(html.split())

        if word_count < 800:
            issues.append({"code": "LOW_WORD_COUNT", "severity": "medium", "message": f"Article has {word_count} words, expected at least 800"})
            score -= 0.25

        if "<h2" not in html:
            issues.append({"code": "MISSING_H2", "severity": "high", "message": "Article contains no <h2> headings"})
            score -= 0.3

        if not article.meta_description or len(article.meta_description) < 60:
            issues.append({"code": "WEAK_META_DESCRIPTION", "severity": "medium", "message": "Meta description missing or too short"})
            score -= 0.15

        if not article.schema_json:
            issues.append({"code": "MISSING_SCHEMA", "severity": "low", "message": "No JSON-LD schema found"})
            score -= 0.1

        if self.factual_fail_hard:
            placeholder_phrases = ["answer placeholder", "this is the answer", "test content"]
            if any(phrase in html.lower() for phrase in placeholder_phrases):
                issues.append({"code": "FACTUAL_HALLUCINATION", "severity": "high", "message": "Article contains placeholder/placeholder text"})
                score -= 0.4

        verdict = self._verdict(score, self.article_min_score)
        if verdict in (AgentDecisionStatus.PASS, AgentDecisionStatus.PASS_WITH_WARNING):
            cluster.status = ClusterStatus.ARTICLE_QC_PASSED
        elif score < 0.4:
            cluster.status = ClusterStatus.ERROR
        else:
            cluster.status = ClusterStatus.ARTICLE_QC_FAILED

        self.record_decision(
            decision_status=verdict,
            site_id=cluster.site_id,
            cluster_id=cluster.id,
            article_id=article.id,
            event_data={"event_type": "article.check", "word_count": word_count},
            score=score,
            reason_json={"issues": issues, "threshold": self.article_min_score},
            recommended_action="proceed_to_publish" if verdict in (AgentDecisionStatus.PASS, AgentDecisionStatus.PASS_WITH_WARNING) else "rewrite_article",
        )

        logger.info(
            "Article QC completed",
            extra_data={"article_id": article.id, "word_count": word_count, "score": round(score, 3), "verdict": verdict.value, "issues": len(issues)},
        )

    @staticmethod
    def _verdict(score: float, threshold: float) -> AgentDecisionStatus:
        if score >= threshold:
            return AgentDecisionStatus.PASS
        if score >= threshold - 0.15:
            return AgentDecisionStatus.PASS_WITH_WARNING
        return AgentDecisionStatus.FAIL