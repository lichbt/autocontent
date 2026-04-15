"""Simple CLI entrypoint for the SEO Content Engine pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure root directory is on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import init_db, get_session
from core.logging import get_logger
from core.models import Site, CMSChoice
from modules import BriefingModule, ClusterModule, IntakeModule, PublishModule, WriterModule, ResearchModule

logger = get_logger("scripts.run_pipeline")


def ensure_site(session, domain: str) -> Site:
    # Normalize domain: strip scheme, www, and trailing slashes
    clean_domain = domain.lower().replace("https://", "").replace("http://", "").rstrip("/")
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]

    site = session.query(Site).filter(Site.domain == clean_domain).first()
    if site:
        return site
    site = Site(domain=clean_domain, cms_type=CMSChoice.WORDPRESS)
    session.add(site)
    session.flush()
    return site


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the SEO Content Engine pipeline")
    parser.add_argument("--site", required=True, help="Site domain, e.g. example.com")
    parser.add_argument("--csv", help="Optional keyword CSV file to import before running pipeline")
    parser.add_argument("--competitors", help="Comma-separated list of competitor URLs for keyword discovery")
    parser.add_argument("--seeds", help="Comma-separated list of seed keywords for Google Suggest expansion")
    parser.add_argument("--skip-publish", action="store_true", help="Skip WordPress publishing step")
    args = parser.parse_args()

    init_db()
    with get_session() as session:
        site = ensure_site(session, args.site)
        logger.info("Pipeline started", extra_data={"site": site.domain, "site_id": site.id})

        if args.csv:
            IntakeModule(session).run_from_csv(Path(args.csv), site.id)

        if args.competitors or args.seeds:
            comp_list = [u.strip() for u in args.competitors.split(",")] if args.competitors else []
            seed_list = [s.strip() for s in args.seeds.split(",")] if args.seeds else []
            logger.info("Running competitor research module")
            res = ResearchModule().run(site, comp_list, seed_list)
            IntakeModule(session).run_from_research(site.id, res["keywords"])

        ClusterModule().run(session)
        BriefingModule(session).run()
        WriterModule(session).run()
        if not args.skip_publish:
            PublishModule(session).run()

        logger.info("Pipeline completed", extra_data={"site": site.domain, "site_id": site.id})


if __name__ == "__main__":
    main()
