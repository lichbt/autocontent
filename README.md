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

## Runbook: local 9router / OpenAI-compatible endpoint

For local LLM drafting, the pipeline can use a local OpenAI-compatible router.

Example `.env`:

```env
9ROUTER_API_KEY=your_local_router_key
9ROUTER_BASE_URL=http://localhost:20128/v1
ROUTER_MODEL=openclaw-combo
```

Notes:
- The local endpoint should expose `/v1/models` and `/v1/chat/completions`
- The current client uses `stream: false` for compatibility with the local router
- A quick health check is:

```bash
curl -X POST http://localhost:20128/v1/chat/completions \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"openclaw-combo","messages":[{"role":"user","content":"Reply with OK"}],"stream":false}'
```

If the response returns HTTP 200 with a normal JSON completion, the pipeline should be able to draft via the local router.

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