# Content Engine

Automated SEO content generation and publishing pipeline.

## Structure

```
content_engine/
├── core/          # Config, DB, logging, event bus
├── modules/       # Pipeline stages: intake, cluster, briefing, writer, publish
├── agents/       # Orchestrator, QC, Recovery, Monitor
├── templates/    # Prompt templates and HTML blocks
├── scripts/      # CLI entrypoints
├── sites/        # Per-site configuration (JSON)
├── SPECIFICATION.md
└── requirements.txt
```

## Quick start

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py --site example.com --csv keywords.csv
```

## Pipeline stages

1. **Intake** — CSV keywords → DB
2. **Cluster** — Group keywords by intent
3. **Brief** — SERP analysis → structured brief JSON
4. **Write** — Article draft from brief
5. **Publish** — Push to WordPress REST API

## Agents

- **Orchestrator** — Routes jobs based on cluster status
- **QC Agent** — Scores briefs and articles
- **Recovery Agent** — Retry/fallback/escalate on failures
- **Monitor Agent** — Health checks and Telegram alerts

## Environment variables

```
DATABASE_URL=sqlite:///content_engine.db
LOG_LEVEL=INFO
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
WP_REQUEST_TIMEOUT_SECONDS=60
```

## Per-site config

Place JSON config files in `sites/` directory:

```json
{
  "site": {
    "domain": "example.com",
    "publish_enabled": true
  },
  "quality_thresholds": {
    "article_min_score": 0.85
  }
}
```