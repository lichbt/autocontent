"""
Configuration management for the SEO Content Engine.

Loads settings from environment variables and supports site-level config overrides.
Designed to support multiple LLM providers routed through direct APIs or aggregators.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_DATABASE_URL = "sqlite:///content_engine.db"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_DIR = "logs"
DEFAULT_ARTIFACTS_DIR = "artifacts"
DEFAULT_DRAFTS_DIR = "drafts"
DEFAULT_PROVIDER_ORDER = [
    "anthropic",
    "openai",
    "gemini",
    "qwen",
    "minimax",
    "kimi",
    "deepseek",
]


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: Optional[str], default: Optional[List[str]] = None) -> List[str]:
    if value is None:
        return list(default or [])
    parts = [item.strip() for item in value.split(",")]
    return [item for item in parts if item]


@dataclass
class ProviderConfig:
    """Configuration for an LLM provider."""

    name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True
    timeout_seconds: int = 60


@dataclass
class AppConfig:
    """Global application configuration."""

    database_url: str = DEFAULT_DATABASE_URL
    log_level: str = DEFAULT_LOG_LEVEL
    log_dir: Path = field(default_factory=lambda: Path(DEFAULT_LOG_DIR))
    artifacts_dir: Path = field(default_factory=lambda: Path(DEFAULT_ARTIFACTS_DIR))
    drafts_dir: Path = field(default_factory=lambda: Path(DEFAULT_DRAFTS_DIR))
    environment: str = "development"
    wp_request_timeout_seconds: int = 60
    provider_priority: List[str] = field(default_factory=lambda: list(DEFAULT_PROVIDER_ORDER))
    providers: Dict[str, ProviderConfig] = field(default_factory=dict)
    site_config_dir: Path = field(default_factory=lambda: Path("sites"))

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        return self.providers.get(name)


@dataclass
class SiteConfig:
    """Site-specific operational config loaded from JSON/YAML-like data."""

    raw: Dict[str, Any]

    @property
    def domain(self) -> Optional[str]:
        return self.raw.get("site", {}).get("domain") or self.raw.get("domain")

    @property
    def cms_type(self) -> str:
        return self.raw.get("site", {}).get("cms", self.raw.get("cms", "wordpress"))

    @property
    def publish_enabled(self) -> bool:
        return bool(self.raw.get("site", {}).get("publish_enabled", True))


def _provider_from_env(prefix: str, name: str, default_model: Optional[str] = None) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        api_key=os.getenv(f"{prefix}_API_KEY"),
        base_url=os.getenv(f"{prefix}_BASE_URL"),
        model=os.getenv(f"{prefix}_MODEL", default_model),
        enabled=_parse_bool(os.getenv(f"{prefix}_ENABLED"), default=True),
        timeout_seconds=int(os.getenv(f"{prefix}_TIMEOUT", "60")),
    )


def load_config() -> AppConfig:
    """Load global app configuration from environment variables."""

    config = AppConfig(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        log_level=os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper(),
        log_dir=Path(os.getenv("LOG_DIR", DEFAULT_LOG_DIR)),
        artifacts_dir=Path(os.getenv("ARTIFACTS_DIR", DEFAULT_ARTIFACTS_DIR)),
        drafts_dir=Path(os.getenv("DRAFTS_DIR", DEFAULT_DRAFTS_DIR)),
        environment=os.getenv("APP_ENV", "development"),
        wp_request_timeout_seconds=int(os.getenv("WP_REQUEST_TIMEOUT_SECONDS", "60")),
        provider_priority=_parse_list(os.getenv("LLM_PROVIDER_PRIORITY"), DEFAULT_PROVIDER_ORDER),
        site_config_dir=Path(os.getenv("SITE_CONFIG_DIR", "sites")),
    )

    config.providers = {
        "openai": _provider_from_env("OPENAI", "openai", "gpt-4o"),
        "anthropic": _provider_from_env("ANTHROPIC", "anthropic", "claude-sonnet-4-20250514"),
        "gemini": _provider_from_env("GEMINI", "gemini", "gemini-2.5-pro"),
        "qwen": _provider_from_env("QWEN", "qwen", None),
        "minimax": _provider_from_env("MINIMAX", "minimax", None),
        "kimi": _provider_from_env("KIMI", "kimi", None),
        "deepseek": _provider_from_env("DEEPSEEK", "deepseek", None),
        "router": _provider_from_env("ROUTER", "router", os.getenv("ROUTER_MODEL", "9router/openclaw-combo")),
    }

    config.log_dir.mkdir(parents=True, exist_ok=True)
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    config.drafts_dir.mkdir(parents=True, exist_ok=True)
    config.site_config_dir.mkdir(parents=True, exist_ok=True)

    return config


def load_site_config(path: str | Path) -> SiteConfig:
    """
    Load a site config file.

    Supports JSON files directly. For YAML-like files, this loader expects JSON-compatible
    content unless PyYAML is introduced later.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Site config not found: {file_path}")

    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        return SiteConfig(raw={})

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Site config must currently be valid JSON. "
            f"Failed to parse {file_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("Site config root must be a JSON object")

    return SiteConfig(raw=data)


CONFIG = load_config()
