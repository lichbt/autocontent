"""Article drafting module."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from core.logging import get_logger
from core.models import Article, ArticleStatus, Cluster, ClusterStatus

logger = get_logger("modules.writer")


class WriterModule:
    """Generate draft articles from stored brief JSON."""

    def __init__(self, session: Session):
        self.session = session

    def run(self) -> int:
        clusters = (
            self.session.query(Cluster)
            .filter(Cluster.status.in_([ClusterStatus.BRIEF_GENERATED, ClusterStatus.BRIEF_QC_PASSED]))
            .all()
        )
        if not clusters:
            logger.info("No clusters pending article drafting")
            return 0

        drafted = 0
        for cluster in clusters:
            try:
                self._draft_article(cluster)
                drafted += 1
            except Exception as exc:
                cluster.status = ClusterStatus.ERROR
                logger.error("Article draft failed", extra_data={"cluster_id": cluster.id, "error": str(exc)})

        self.session.commit()
        return drafted

    def _draft_article(self, cluster: Cluster) -> None:
        brief = cluster.brief_json or {}
        primary_keyword = str(brief.get("primary_keyword") or cluster.primary_keyword.raw_keyword)
        target_word_count = int(brief.get("target_word_count") or 1500)
        outline = brief.get("outline") or []

        title = primary_keyword.strip().title()
        slug = self._slugify(primary_keyword)
        intro = self._paragraph(primary_keyword, "introduction")
        sections: list[str] = []
        faq_items: list[dict[str, str]] = []

        for item in outline:
            h2 = str(item.get("h2") or "").strip()
            if not h2:
                continue
            body = self._paragraph(primary_keyword, h2)
            sections.append(f"<h2>{h2}</h2>\n<p>{body}</p>")
            if h2.lower() == "frequently asked questions":
                faq_items = self._faq_items(primary_keyword)
                for faq in faq_items:
                    sections.append(f"<h3>{faq['question']}</h3>\n<p>{faq['answer']}</p>")

        html = "\n".join([
            f"<h1>{title}</h1>",
            f"<p>{intro}</p>",
            *sections,
        ])
        meta_description = self._meta_description(primary_keyword)
        schema_json = self._schema(primary_keyword, faq_items if faq_items else None)

        if cluster.article:
            article = cluster.article
            article.title = title
            article.slug = slug
            article.content_html = html
            article.meta_description = meta_description
            article.schema_json = schema_json
            article.status = ArticleStatus.DRAFT
        else:
            article = Article(
                cluster_id=cluster.id,
                title=title,
                slug=slug,
                content_html=html,
                meta_description=meta_description,
                schema_json=schema_json,
                status=ArticleStatus.DRAFT,
            )
            self.session.add(article)

        cluster.status = ClusterStatus.ARTICLE_DRAFTED
        logger.info(
            "Article drafted",
            extra_data={"cluster_id": cluster.id, "slug": slug, "target_word_count": target_word_count},
        )

    @staticmethod
    def _paragraph(primary_keyword: str, section: str) -> str:
        return (
            f"This section explains {section.lower()} for {primary_keyword}. "
            f"It focuses on clarity, practical decision factors, and SEO-friendly coverage for readers researching {primary_keyword}."
        )

    @staticmethod
    def _faq_items(primary_keyword: str) -> list[dict[str, str]]:
        return [
            {
                "question": f"What should you look for when choosing {primary_keyword}?",
                "answer": f"Focus on fit, features, quality signals, and how well the option matches the intent behind {primary_keyword}.",
            },
            {
                "question": f"Is {primary_keyword} worth it?",
                "answer": f"For most buyers, {primary_keyword} is worth evaluating when the features align with your budget and use case.",
            },
        ]

    @staticmethod
    def _meta_description(primary_keyword: str) -> str:
        text = f"Learn how to evaluate {primary_keyword} with a practical guide covering key considerations, top options, and FAQs."
        return text[:155]

    @staticmethod
    def _schema(primary_keyword: str, faq_items: list[dict[str, str]] | None) -> dict[str, Any]:
        if faq_items:
            return {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in faq_items
                ],
            }
        return {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": primary_keyword,
        }

    @staticmethod
    def _slugify(value: str) -> str:
        import re

        value = value.lower().strip()
        value = re.sub(r"[^a-z0-9\s-]", "", value)
        value = re.sub(r"\s+", "-", value)
        return value[:80].strip("-")
