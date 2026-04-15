"""WordPress publishing module."""

from __future__ import annotations

import requests
from requests.auth import HTTPBasicAuth
from sqlalchemy.orm import Session

from core.config import CONFIG
from core.logging import get_logger
from core.models import Article, ArticleStatus, Cluster, ClusterStatus, Site

logger = get_logger("modules.publish")


class PublishModule:
    """Publish drafted articles to WordPress via REST API."""

    def __init__(self, session: Session):
        self.session = session

    def run(self) -> int:
        articles = (
            self.session.query(Article)
            .join(Cluster, Article.cluster_id == Cluster.id)
            .filter(Cluster.status == ClusterStatus.ARTICLE_QC_PASSED, Article.status == ArticleStatus.DRAFT)
            .all()
        )
        if not articles:
            logger.info("No articles pending WordPress publishing")
            return 0

        published = 0
        for article in articles:
            try:
                self._publish(article)
                published += 1
            except Exception as exc:
                article.status = ArticleStatus.ERROR
                logger.error("WordPress publish failed", extra_data={"article_id": article.id, "error": str(exc)})

        self.session.commit()
        return published

    def _publish(self, article: Article) -> None:
        cluster = article.cluster
        site = self.session.get(Site, cluster.site_id)
        if not site:
            raise ValueError(f"Site not found for cluster {cluster.id}")

        api_config = site.cms_api_config or {}
        wp_url = str(api_config.get("url") or "").rstrip("/")
        username = str(api_config.get("username") or "")
        app_password = str(api_config.get("app_password") or "")
        publish_status = str(api_config.get("publish_status") or "publish")
        if not wp_url or not username or not app_password:
            raise ValueError(f"Missing WordPress credentials for site {site.domain}")

        payload = {
            "title": article.title,
            "slug": article.slug,
            "content": article.content_html,
            "status": publish_status,
            "excerpt": article.meta_description,
        }

        response = requests.post(
            f"{wp_url}/wp-json/wp/v2/posts",
            json=payload,
            auth=HTTPBasicAuth(username, app_password),
            timeout=CONFIG.wp_request_timeout_seconds,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

        article.published_url = data.get("link")
        article.status = ArticleStatus.PUBLISHED
        cluster.status = ClusterStatus.PUBLISHED
        logger.info("Article published to WordPress", extra_data={"article_id": article.id, "url": article.published_url})
