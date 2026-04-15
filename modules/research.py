"""Competitor URL research module.
Scrapes competitor sites to discover target keywords.
"""

from __future__ import annotations

import re
import urllib.parse
from collections import Counter
from typing import Any

import requests

from core.logging import get_logger
from core.models import Site

logger = get_logger("modules.research")


# Common SEO keyword patterns to look for in titles, meta
KEYWORD_PATTERNS = [
    r"<title>([^<]{10,200})</title>",
    r'<meta name="keywords" content="([^"]+)"',
    r'<meta name="description" content="([^"]+)"',
    r"<h1[^>]*>([^<]+)</h1>",
    r"<h2[^>]*>([^<]+)</h2>",
    r"<h3[^>]*>([^<]+)</h3>",
]


# Seed keywords for Google Suggest expansion
SUGGEST_MODIFIERS = [
    "",
    "best",
    "top",
    "reviews",
    "2024",
    "2025",
    "2026",
    "cheap",
    "free",
    "online",
    "software",
    "app",
    "website",
    "solution",
    "comparison",
    "alternative",
]


class ResearchModule:
    """Extract keywords from competitor URLs and seed terms."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; SEOContentEngine/1.0)",
        })

    def run(
        self,
        site: Site,
        competitor_urls: list[str],
        seed_keywords: list[str],
    ) -> dict[str, Any]:
        """
        Run competitor research.

        Args:
            site: Site model for context
            competitor_urls: List of competitor URLs to analyze
            seed_keywords: Seed terms to expand via Google Suggest

        Returns:
            Dict with 'keywords': [{keyword, source, relevance}, ...]
        """
        found_keywords: list[dict[str, Any]] = []
        seen = set()

        # 1. Extract from competitor sites
        for url in competitor_urls:
            if not url.startswith("http"):
                url = "https://" + url

            try:
                kwds = self._extract_from_url(url)
                for kw in kwds:
                    if kw not in seen:
                        seen.add(kw)
                        found_keywords.append({
                            "keyword": kw,
                            "source": "competitor",
                            "url": url,
                            "relevance": "high",
                        })
                logger.info(f"Extracted {len(kwds)} keywords from {url}")
            except Exception as exc:
                logger.warning(f"Failed to fetch {url}", extra_data={"error": str(exc)})

        # 2. Expand via Google Suggest from seed keywords
        for seed in seed_keywords:
            suggestions = self._google_suggest(seed)
            for sug in suggestions:
                if sug not in seen:
                    seen.add(sug)
                    found_keywords.append({
                        "keyword": sug,
                        "source": "suggest",
                        "seed": seed,
                        "relevance": "medium",
                    })

        # 3. Deduplicate and rank by source priority
        ranked = self._rank_keywords(found_keywords)

        logger.info(
            "Competitor research completed",
            extra_data={
                "total_keywords": len(ranked),
                "competitor_urls": len(competitor_urls),
                "seed_keywords": len(seed_keywords),
            },
        )
        return {"keywords": ranked}

    def _extract_from_url(self, url: str) -> list[str]:
        """Extract keyword phrases from a URL's HTML."""
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            html = response.text
        except Exception as exc:
            logger.debug(f"Fetch error {url}: {exc}")
            return []

        keywords: list[str] = []

        # Extract title
        title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
            # Clean entity codes
            title = re.sub(r"&#?\w+;", " ", title)
            # Split into phrases
            for part in re.split(r"[\|\-:>", title):
                part = part.strip()
                if 3 < len(part) < 60:
                    keywords.append(part)

        # Extract meta description
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content="([^"]+)"',
            html,
            re.IGNORECASE,
        )
        if desc_match:
            desc = desc_match.group(1)
            for word in desc.split():
                word = word.strip()
                if 4 < len(word) < 40:
                    keywords.append(word)

        # Extract headings
        for pattern in [r"<h1[^>]*>([^<]+)</h1>", r"<h2[^>]*>([^<]+)</h2>"]:
            for match in re.finditer(pattern, html, re.IGNORECASE):
                heading = match.group(1).strip()
                if 3 < len(heading) < 80:
                    keywords.append(heading)

        # Deduplicate and clean
        cleaned = []
        for kw in keywords:
            kw = re.sub(r"[^\w\s\-\']", "", kw).strip()
            if kw and 3 < len(kw) < 60:
                cleaned.append(kw.lower())
        return list(set(cleaned))

    def _google_suggest(self, seed: str) -> list[str]:
        """Get keyword suggestions from Google Suggest API."""
        suggestions = set()
        base_seed = seed.strip().lower()

        # Try seed + modifiers
        for mod in SUGGEST_MODIFIERS:
            if mod:
                query = f"{mod} {base_seed}"
            else:
                query = base_seed

            try:
                response = self.session.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "q": query},
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                if data and len(data) > 1:
                    for item in data[1]:
                        suggestions.add(item.strip().lower())
            except Exception:
                pass

        # Also try "[seed] vs", "[seed] alternative", etc.
        for suffix in [" vs", " alternative", " comparison"]:
            query = base_seed + suffix
            try:
                response = self.session.get(
                    "https://suggestqueries.google.com/complete/search",
                    params={"client": "firefox", "q": query},
                    timeout=10,
                )
                response.raise_for_status()
                data = response.json()
                if data and len(data) > 1:
                    for item in data[1]:
                        suggestions.add(item.strip().lower())
            except Exception:
                pass

        # Filter to phrases containing the seed
        filtered = [s for s in suggestions if base_seed in s]
        return list(set(filtered))[:50]

    def _rank_keywords(self, keywords: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank keywords by source priority."""
        source_priority = {"competitor": 3, "suggest": 1}

        ranked = sorted(
            keywords,
            key=lambda k: (source_priority.get(k.get("source"), 0), k.get("keyword", "")),
            reverse=True,
        )
        return ranked