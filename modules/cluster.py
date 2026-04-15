"""Keyword clustering module."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from sqlalchemy.orm import Session

from core.logging import get_logger
from core.models import Cluster, ClusterStatus, Keyword, KeywordStatus, SearchIntent

logger = get_logger("modules.cluster")


class ClusterModule:
    """Create simple intent-aware keyword clusters."""

    def __init__(self, similarity_threshold: float = 0.78, max_cluster_size: int = 15):
        self.similarity_threshold = similarity_threshold
        self.max_cluster_size = max_cluster_size

    def run(self, session: Session) -> int:
        keywords = (
            session.query(Keyword)
            .filter(Keyword.status == KeywordStatus.PENDING_CLUSTER)
            .order_by(Keyword.site_id, Keyword.search_volume.desc().nullslast(), Keyword.raw_keyword.asc())
            .all()
        )
        if not keywords:
            logger.info("No keywords pending clustering")
            return 0

        by_site: dict[str, list[Keyword]] = defaultdict(list)
        for keyword in keywords:
            by_site[keyword.site_id].append(keyword)

        created = 0
        for site_keywords in by_site.values():
            created += self._cluster_site_keywords(session, site_keywords)

        session.commit()
        logger.info("Keyword clustering completed", extra_data={"clusters_created": created})
        return created

    def _cluster_site_keywords(self, session: Session, keywords: list[Keyword]) -> int:
        created = 0
        groups: dict[tuple[str, str], list[Keyword]] = defaultdict(list)

        for keyword in keywords:
            intent = keyword.intent or SearchIntent.INFORMATIONAL
            bucket = self._bucket_keyword(keyword.raw_keyword)
            groups[(intent.value, bucket)].append(keyword)

        for (_, _), members in groups.items():
            for chunk in self._chunk(members, self.max_cluster_size):
                primary = max(chunk, key=lambda item: item.search_volume or 0)
                cluster = Cluster(
                    site_id=primary.site_id,
                    primary_keyword_id=primary.id,
                    secondary_keyword_ids=[item.id for item in chunk if item.id != primary.id],
                    search_intent=primary.intent or SearchIntent.INFORMATIONAL,
                    status=ClusterStatus.PENDING_BRIEF,
                )
                session.add(cluster)
                for item in chunk:
                    item.status = KeywordStatus.CLUSTERED
                created += 1

        return created

    @staticmethod
    def _bucket_keyword(raw_keyword: str) -> str:
        words = [word for word in raw_keyword.lower().split() if word]
        return " ".join(words[:2]) if words else raw_keyword.lower().strip()

    @staticmethod
    def _chunk(items: list[Keyword], size: int) -> Iterable[list[Keyword]]:
        for index in range(0, len(items), size):
            yield items[index:index + size]
