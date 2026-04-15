# Engineering Specification: SEO Content Engine

**Version:** 1.0  
**Date:** April 15, 2026  
**Author:** Aria (Lead Automation Architect)

---

## 1. Objective

To build a modular, Python-based, agent-augmented system for programmatic SEO content generation and publishing. The system automates keyword-to-CMS publishing with robust monitoring, QCs, and error recovery.

---

## 2. Scope

### In-Scope (V1)
- Keyword ingestion from CSV/APIs
- Keyword clustering and search intent mapping
- Automated content brief generation via SERP scraping (Playwright + BeautifulSoup)
- Multi-stage AI content generation (outline → sections → FAQ schema)
- WordPress publishing (REST API)
- Agent-based orchestration, quality control, and error recovery
- Event-driven communication and notifications
- Site-specific configuration

### Out-of-Scope
- Real-time SERP updates
- Complex a/b testing
- Image/video generation (only alt-text)
- BI dashboards (export to external tools)
- Multi-CMS support (WP only for V1)

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Pipeline Modules (Stateless workers)                               │
│  - intake.py      : Keywords → DB                                   │
│  - cluster.py     : Keyword → Clusters                              │
│  - brief.py       : SERP scrape → Brief JSON                        │
│  - writer.py      : Brief → Outline → Article HTML                  │
│  - publish.py     : Article → WordPress REST API                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Agents (Orchestrator, QC, Recovery, Monitor)                       │
│  - Orchestrator   : Routes jobs based on state & decisions          │
│  - QC Agent       : Quality scoring + compliance checks             │
│  - Recovery Agent : Diagnose failures + retry/escalate              │
│  - Monitor Agent  : Health dashboards + alerting                    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Database (PostgreSQL or SQLite)                                    │
│  - sites, keywords, clusters, articles                              │
│  - pipeline_runs, job_queue, incidents, notifications               │
│  - agent_decisions, artifacts                                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Config Layer (per-site YAML/JSON)                                  │
│  - CMS credentials, LLM models, quality thresholds, alerts          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Entities (SQLAlchemy Models)

### `sites`
- `site_id` (PK, UUID)
- `domain` (String, Unique)
- `cms_type` (Enum: 'wordpress')
- `cms_api_config` (JSONB)
- `config_yaml` (JSONB) — site-specific rules

### `keywords`
- `keyword_id` (PK, UUID)
- `site_id` (FK)
- `raw_keyword`, `search_volume`, `difficulty`, `intent`, `status`

### `clusters`
- `cluster_id` (PK, UUID)
- `site_id`, `primary_keyword_id`, `secondary_keyword_ids` (JSON)
- `search_intent`, `status`, `brief_json` (JSON)

### `articles`
- `article_id` (PK, UUID)
- `cluster_id` (Unique FK), `title`, `slug`, `content_html`
- `meta_description`, `schema_json`, `published_url`, `status`

### `job_queue`
- Tracks all pending/running/stuck jobs per pipeline stage

### `agent_decisions`
- Stores every agent verdict with reasons, scores, and next steps

### `incidents`
- Records failures, severity, root cause, resolution

### `notifications`
- Telegram alerts with formatted messages

---

## 5. Pipeline Modules

### `01_intake.py`
**Input:** CSV or API (Ahrefs/SEMrush/DataForSEO)  
**Output:** Keywords in DB, `status='pending_cluster'`  
**Logic:** Deduplication, intent inference, branded keyword filtering

### `02_cluster.py`
**Input:** Pending keywords per site  
**Output:** Clusters in DB, `status='pending_brief'`  
**Logic:** Sentence-transformers embeddings (cosine similarity ≥ threshold), max 15 keywords per cluster

### `03_briefing.py`
**Input:** Primary keyword  
**Output:** `brief_json` (competitor H2s, target word count, entities, outline)  
**Logic:** Playwright SERP scrape → top 3 URLs → extract structure → LLM brief synthesis

### `04_writer.py`
**Input:** `brief_json`  
**Output:** Article HTML with schema  
**Logic:** 1) Outline → 2) Intro → 3) Sections (loop) → 4) FAQ schema → 5) Assembly

### `05_publish.py`
**Input:** Article draft  
**Output:** Live WordPress post  
**Logic:** REST API `/wp-json/wp/v2/posts`, error handling, URL mapping

---

## 6. Agents

### Orchestrator Agent
- **Role:** Central workflow router
- **Triggers:** Module completion events, QC verdicts, Recovery decisions
- **Output:** Next `job_queue` entry or status update

### QC Agent
- **Role:** Quality gatekeeper
- **Checks:**
  - **Structural** (H2/H3 presence, section order)
  - **SEO** (keyword density, meta description, internal links)
  - **Topical** (entity coverage vs brief)
  - **Readability** (no fluff, clear formatting)
  - **Factual** (no hallucinations, consistency)
- **Output:** Structured verdict (`score`, `issues`, `recommended_action`)

### Recovery Agent
- **Role:** Failure diagnosis and recovery
- **Logic Tree:**
  - Scraping fails → retry → fallback scraper → cached SERP → manual review
  - LLM fails → retry → lower max tokens → strict JSON mode → fallback model → manual review
  - Publish fails → sanitize payload → retry → local save → alert
- **Output:** `recovery.action_taken` event or escalation

### Monitor Agent
- **Role:** Operational visibility
- **Checks:**
  - Job queue stuck times
  - Success/failure rates
  - LLM model fallback usage
  - Incident pattern detection
- **Output:** Digest alerts (medium) or immediate Telegram (high/critical)

---

## 7. Event Bus

```
event_types = [
  'keyword.ingested',
  'cluster.created',
  'brief.generated',
  'brief.failed',
  'article.generated',
  'article.qc_passed',
  'article.qc_failed',
  'publish.succeeded',
  'publish.failed',
  'job.stuck',
  'agent.escalation',
]
```

Event payload:
```json
{
  "event_type": "article.qc_failed",
  "site_id": "uuid",
  "cluster_id": "uuid",
  "article_id": "uuid",
  "timestamp": "ISO8601",
  "data": { ... }
}
```

---

## 8. Quality Scorecard (per-site configurable)

| Dimension | Weight | Pass Threshold |
|---|---|---|
| Structural compliance | 20% | All required H2s, sections present |
| SEO compliance | 25% | Keyword density 1–2.5%, meta + links |
| Topical coverage | 25% | Entity coverage ≥ brief targets |
| Readability/utility | 15% | No repetitive paragraphs, clear flow |
| Factual confidence | 15% | No hallucinated facts |

Overall score = weighted sum  
- `≥ 0.85` → pass  
- `0.70–0.84` → pass_with_warning  
- `< 0.70` → fail  

---

## 9. Retry Policy (per-site configurable)

- `max_attempts`: default 3
- `retry_delay_strategy`: exponential_backoff `[60s, 300s, 900s]`
- `llm_model_fallbacks`: list fallback models
- `use_cached_serp_on_scrape_fail`: boolean

---

## 10. Human Escalation (per-site configurable)

| Level | Trigger | Notification |
|---|---|---|
| **Low** | Self-corrected failures | Logged only |
| **Medium** | >3 QC fails in time period, scraper degradation, stuck >2h | Digest alert |
| **High** | Module-wide failures, CMS auth errors, LLM outage | Immediate Telegram |

---

## 11. Deployment (V1)

- **Language:** Python 3.9+  
- **Database:** SQLite (development), PostgreSQL (prod)  
- **Execution:** CLI or cron  
- **CMS Integration:** WordPress REST API only  
- **LLM Providers:** OpenAI, Anthropic, Google, local (auto-fallback)

---

## 12. Directory Structure

```
content_engine/
├── core/
│   ├── __init__.py
│   ├── db.py               # SQLAlchemy engine, base, session factory
│   ├── models.py           # All 10 tables as models
│   ├── config.py           # Site config loader, env defaults
│   ├── event_bus.py        # Simple in-process event dispatch
│   └── logging.py          # Structured JSON logs, file + console
├── modules/
│   ├── 01_intake.py
│   ├── 02_cluster.py
│   ├── 03_briefing.py
│   ├── 04_writer.py
│   └── 05_publish.py
├── agents/
│   ├── orchestrator.py     # Main routing logic
│   ├── qc.py               # QC Agent with scorecard
│   ├── recovery.py         # Failure diagnosis + recovery
│   └── monitor.py          # Health checks + alerts
├── templates/
│   ├── prompts/
│   │   ├── brief_system.txt
│   │   ├── outline_system.txt
│   │   ├── section_system.txt
│   │   └── faq_system.txt
│   └── html/
│       ├── table_block.html
│       └── pros_cons.html
├── scripts/
│   ├── run_pipeline.py
│   └── run_agent.py
├── requirements.txt
└── SPECIFICATION.md (this file)
```

---

## 13. acceptance criteria (V1)

- [ ] sqlite database created with all 10 tables
- [ ] `01_intake.py` reads CSV, deduplicates, inserts keywords
- [ ] `02_cluster.py` clusters keywords using sentence-transformers
- [ ] `03_briefing.py` scrapes SERP, extracts H2/H3, generates brief JSON
- [ ] `04_writer.py` produces HTML article + schema from brief
- [ ] `05_publish.py` pushes to WordPress REST API
- [ ] QC Agent scores articles with weightings per dimension
- [ ] Recovery Agent handles timeout/429/scrape-block/JSON-fail
- [ ] Orchestrator routes events → job_queue updates
- [ ] Monitor Agent tracks stuck jobs and failure rates
- [ ] Telegram notifications for high/critical incidents
- [ ] Per-site config YAML overrides defaults
- [ ] Single CLI entrypoint (`python scripts/run_pipeline.py --site example.com`)

---

**Next:** Implement `core/db.py` + `core/models.py`, then the modules in order.
