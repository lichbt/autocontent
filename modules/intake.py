"""Keyword intake module for CSV imports."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from core.logging import get_logger
from core.models import Keyword, KeywordStatus, SearchIntent, Site

logger = get_logger("modules.intake")


class IntakeModule:
    """Import keywords into the database for a given site."""

    def __init__(self, session: Session):
        self.session = session

    def run_from_csv(self, file_path: str | Path, site_id: str) -> dict[str, int]:
        site = self.session.get(Site, site_id)
        if not site:
            raise ValueError(f"Site not found: {site_id}")

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        total_rows = 0
        inserted = 0
        skipped = 0

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for raw_row in reader:
                total_rows += 1
                row = {str(k).strip().lower(): v for k, v in raw_row.items() if k is not None}

                keyword_text = self._pick(row, ["keyword", "query", "term"])
                if not keyword_text:
                    skipped += 1
                    continue

                keyword_text = keyword_text.strip().lower()
                existing = (
                    self.session.query(Keyword)
                    .filter(Keyword.site_id == site_id, Keyword.raw_keyword == keyword_text)
                    .first()
                )
                if existing:
                    skipped += 1
                    continue

                keyword = Keyword(
                    site_id=site_id,
                    raw_keyword=keyword_text,
                    search_volume=self._to_int(self._pick(row, ["search_volume", "volume"])),
                    difficulty=self._to_int(self._pick(row, ["difficulty", "keyword difficulty", "kd"])),
                    intent=self._parse_intent(self._pick(row, ["intent"])),
                    status=KeywordStatus.PENDING_CLUSTER,
                )
                self.session.add(keyword)
                inserted += 1

        self.session.commit()
        result = {"total_rows": total_rows, "inserted": inserted, "skipped": skipped}
        logger.info("CSV intake completed", extra_data={"site_id": site_id, **result})
        return result

    @staticmethod
    def _pick(row: dict[str, object], keys: list[str]) -> Optional[str]:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    @staticmethod
    def _to_int(value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            return int(value.replace(",", "").strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_intent(value: Optional[str]) -> Optional[SearchIntent]:
        if not value:
            return None
        try:
            return SearchIntent(value.strip().lower())
        except ValueError:
            return None
