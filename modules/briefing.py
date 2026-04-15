"""SERP-based brief generation module."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse, unquote

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from core.logging import get_logger
from core.models import Cluster, ClusterStatus

logger = get_logger("modules.briefing")


class BriefingModule:
    """Generate a simple structured brief from SERP pages."""

    def __init__(self, session: Session, timeout_seconds: int = 20):
        self.session = session
        self.http = requests.Session()
        self.http.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ContentEngine/1.0)"})
        self.timeout_seconds = timeout_seconds

    def run(self) -> int:
        clusters = (
            self.session.query(Cluster)
            .filter(Cluster.status == ClusterStatus.PENDING_BRIEF)
            .all()
        )
        if not clusters:
            logger.info("No clusters pending brief generation")
            return 0

        completed = 0
        for cluster in clusters:
            try:
                self._generate_brief(cluster)
                completed += 1
            except Exception as exc:
                cluster.status = ClusterStatus.ERROR
                logger.error("Brief generation failed", extra_data={"cluster_id": cluster.id, "error": str(exc)})

        self.session.commit()
        return completed

    def _generate_brief(self, cluster: Cluster) -> None:
        primary_keyword = cluster.primary_keyword.raw_keyword
        urls = self._scrape_serp(primary_keyword, top_n=3)
        competitor_analysis: list[dict[str, Any]] = []
        all_h2s: list[str] = []
        word_counts: list[int] = []
        schema_types: list[str] = []

        for url in urls:
            data = self._scrape_competitor(url)
            if not data:
                continue
            competitor_analysis.append(data)
            all_h2s.extend(data.get("h2s", []))
            if data.get("word_count"):
                word_counts.append(int(data["word_count"]))
            if data.get("schema_type"):
                schema_types.append(str(data["schema_type"]))

        common_h2s = [item for item, _ in Counter(all_h2s).most_common(5)]
        target_word_count = int(sum(word_counts) / len(word_counts)) if word_counts else 1500
        target_word_count = max(1000, min(target_word_count, 3000))
        schema_type = "FAQPage" if "FAQPage" in schema_types else "Article"

        outline = [{"h2": "Introduction", "word_target": max(120, int(target_word_count * 0.1))}]
        if common_h2s:
            section_target = max(180, int(target_word_count * 0.65 / len(common_h2s)))
            outline.extend({"h2": h2, "word_target": section_target} for h2 in common_h2s)
        else:
            outline.extend([
                {"h2": "Key Considerations", "word_target": 300},
                {"h2": "Best Options", "word_target": 400},
                {"h2": "How to Choose", "word_target": 300},
            ])
        if schema_type == "FAQPage":
            outline.append({"h2": "Frequently Asked Questions", "word_target": max(180, int(target_word_count * 0.15))})

        cluster.brief_json = {
            "primary_keyword": primary_keyword,
            "target_word_count": target_word_count,
            "competitor_analysis": competitor_analysis,
            "entities": [],
            "schema_type": schema_type,
            "outline": outline,
        }
        cluster.status = ClusterStatus.BRIEF_GENERATED
        logger.info("Brief generated", extra_data={"cluster_id": cluster.id, "keyword": primary_keyword})

    def _scrape_serp(self, keyword: str, top_n: int = 3) -> list[str]:
        response = self.http.get("https://html.duckduckgo.com/html/", params={"q": keyword}, timeout=self.timeout_seconds)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        urls: list[str] = []
        for link in soup.select("a.result__a"):
            href = link.get("href")
            clean = self._extract_target_url(href)
            if clean and clean not in urls:
                urls.append(clean)
            if len(urls) >= top_n:
                break
        return urls

    @staticmethod
    def _extract_target_url(href: Optional[str]) -> Optional[str]:
        if not href:
            return None
        if href.startswith("http"):
            parsed = urlparse(href)
            query = parse_qs(parsed.query)
            if "uddg" in query and query["uddg"]:
                return unquote(query["uddg"][0])
            return href
        return None

    def _scrape_competitor(self, url: str) -> Optional[dict[str, Any]]:
        try:
            response = self.http.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        h2s = [item.get_text(" ", strip=True) for item in soup.find_all("h2")][:10]
        h3s = [item.get_text(" ", strip=True) for item in soup.find_all("h3")][:10]
        text = soup.get_text(" ", strip=True)
        word_count = len(text.split())
        schema_type = None
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            try:
                payload = json.loads(script.string or "")
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("@type"):
                schema_type = str(payload["@type"])
                break

        return {
            "url": url,
            "h2s": h2s,
            "h3s": h3s,
            "word_count": word_count,
            "schema_type": schema_type,
        }
