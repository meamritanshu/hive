"""HiveCore settings management.

Provides a Pydantic-based settings model with TOML file persistence.
Settings are loaded from ~/.hivecore/config.toml by default.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

# Default data directory
DEFAULT_DATA_DIR = Path.home() / ".hivecore"
DEFAULT_CONFIG_PATH = DEFAULT_DATA_DIR / "config.toml"


class LLMSettings(BaseModel):
    """LLM provider configuration."""

    model: str = Field(default="gpt-4o", description="Default model identifier.")
    provider: str = Field(
        default="litellm",
        description="LLM provider (litellm, openai, anthropic, google, ollama).",
    )
    api_key: Optional[str] = Field(default=None, description="API key for the LLM provider.")
    api_base: Optional[str] = Field(default=None, description="Custom API base URL.")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature.")
    max_tokens: int = Field(default=4096, gt=0, description="Max tokens per response.")
    streaming: bool = Field(default=True, description="Enable streaming responses.")
    timeout: int = Field(default=120, gt=0, description="Request timeout in seconds.")


class MemorySettings(BaseModel):
    """Memory system configuration."""

    backend: str = Field(
        default="sqlite", description="Memory backend (sqlite, chromadb)."
    )
    data_dir: Path = Field(
        default=DEFAULT_DATA_DIR / "memory",
        description="Directory for memory data storage.",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model for vector memory.",
    )
    embedding_provider: str = Field(
        default="openai",
        description="Embedding provider (openai, local, ollama).",
    )
    max_short_term_messages: int = Field(
        default=50, gt=0, description="Max messages in short-term memory buffer."
    )
    compaction_threshold: int = Field(
        default=4000,
        gt=0,
        description="Token count threshold that triggers memory compaction.",
    )
    retrieval_top_k: int = Field(
        default=10, gt=0, description="Number of results for memory retrieval."
    )
    bm25_weight: float = Field(
        default=0.3, ge=0.0, le=1.0, description="BM25 weight in hybrid retrieval."
    )
    vector_weight: float = Field(
        default=0.7, ge=0.0, le=1.0, description="Vector weight in hybrid retrieval."
    )


class SkillsSettings(BaseModel):
    """Skills system configuration."""

    directory: Path = Field(
        default=DEFAULT_DATA_DIR / "skills",
        description="Directory for custom skill files.",
    )
    auto_load: bool = Field(
        default=True, description="Auto-load skills from the skill directory."
    )
    hot_reload: bool = Field(
        default=False, description="Enable hot-reload for skill changes."
    )
    max_execution_time: int = Field(
        default=300, gt=0, description="Max execution time per skill in seconds."
    )
    max_memory_mb: int = Field(
        default=512, gt=0, description="Max memory per skill execution in MB."
    )
    # Security: permissions granted to all skills by default.
    # Skills that declare permissions outside this list must have a
    # per-skill <skill_name>.toml allow-list granting the extra permissions.
    # Empty list = deny-by-default (recommended for production).
    default_permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Permissions granted to all skills without a per-skill allow-list. "
            "Valid tokens: network, filesystem, shell, secrets:<KEY>. "
            "Empty = deny-by-default."
        ),
    )
    # Execution sandbox: subprocess (default) or docker (requires Docker Engine).
    sandbox_type: str = Field(
        default="subprocess",
        description="Skill execution sandbox: 'subprocess' or 'docker'.",
    )


class WebSettings(BaseModel):
    """Web console configuration."""

    host: str = Field(default="127.0.0.1", description="Web console host.")
    port: int = Field(default=8088, ge=1, le=65535, description="Web console port.")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origins.",
    )


class ChannelConfig(BaseModel):
    """Base configuration for a communication channel."""

    enabled: bool = Field(default=False, description="Whether this channel is enabled.")
    token: Optional[str] = Field(default=None, description="Auth token for the channel.")


class DiscordChannelConfig(ChannelConfig):
    """Discord-specific configuration."""

    guild_ids: list[str] = Field(
        default_factory=list, description="Discord guild IDs to connect to."
    )


class TelegramChannelConfig(ChannelConfig):
    """Telegram-specific configuration."""

    allowed_chat_ids: list[int] = Field(
        default_factory=list,
        description="Telegram chat IDs allowed to interact with the agent.",
    )


class IMessageChannelConfig(ChannelConfig):
    """iMessage-specific configuration."""

    allowed_contacts: list[str] = Field(
        default_factory=list,
        description="Phone numbers or emails allowed to interact.",
    )


class ChannelsSettings(BaseModel):
    """Multi-channel configuration."""

    discord: DiscordChannelConfig = Field(default_factory=DiscordChannelConfig)
    telegram: TelegramChannelConfig = Field(default_factory=TelegramChannelConfig)
    imessage: IMessageChannelConfig = Field(default_factory=IMessageChannelConfig)


class SchedulerSettings(BaseModel):
    """Scheduler configuration."""

    enabled: bool = Field(default=True, description="Enable the task scheduler.")
    heartbeat_interval: int = Field(
        default=3600, gt=0, description="Heartbeat interval in seconds."
    )
    max_concurrent_jobs: int = Field(
        default=5, gt=0, description="Max concurrent scheduled jobs."
    )


class AgentSettings(BaseModel):
    """Agent behavior configuration."""

    system_prompt: str = Field(
        default=(
            "You are HiveCore, a helpful personal AI assistant. "
            "You have access to various tools and skills to help the user. "
            "You maintain long-term memory of conversations and user preferences. "
            "Be concise, accurate, and proactive."
        ),
        description="System prompt for the agent.",
    )
    persona: str = Field(default="default", description="Active agent persona name.")
    max_iterations: int = Field(
        default=20, gt=0, description="Max ReAct loop iterations per turn."
    )
    verbose: bool = Field(default=False, description="Enable verbose agent logging.")


class HiveSettings(BaseModel):
    """Root settings model for HiveCore."""

    llm: LLMSettings = Field(default_factory=LLMSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    skills: SkillsSettings = Field(default_factory=SkillsSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    channels: ChannelsSettings = Field(default_factory=ChannelsSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    data_dir: Path = Field(default=DEFAULT_DATA_DIR, description="Root data directory.")
    log_level: str = Field(default="INFO", description="Logging level.")


# --- Settings persistence ---

_cached_settings: Optional[HiveSettings] = None


def get_settings(config_path: Optional[Path] = None) -> HiveSettings:
    """Load settings from TOML config file, with caching.

    Args:
        config_path: Path to the config file. Defaults to ~/.hivecore/config.toml.

    Returns:
        The loaded HiveSettings instance.
    """
    global _cached_settings
    if _cached_settings is not None and config_path is None:
        return _cached_settings

    path = config_path or DEFAULT_CONFIG_PATH

    if path.exists():
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        with open(path, "rb") as f:
            data = tomllib.load(f)
        settings = HiveSettings(**data)
    else:
        settings = HiveSettings()

    if config_path is None:
        _cached_settings = settings

    return settings


def save_settings(settings: HiveSettings, config_path: Optional[Path] = None) -> None:
    """Save settings to TOML config file.

    Args:
        settings: The settings to save.
        config_path: Path to the config file. Defaults to ~/.hivecore/config.toml.
    """
    import tomli_w

    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, handling Path objects
    data = _settings_to_dict(settings)

    with open(path, "wb") as f:
        tomli_w.dump(data, f)

    # Update cache
    global _cached_settings
    if config_path is None:
        _cached_settings = settings


def _settings_to_dict(obj: BaseModel) -> dict:
    """Recursively convert a Pydantic model to a dict suitable for TOML serialization."""
    return _clean_for_toml(obj.model_dump())


def _clean_for_toml(value: Any) -> Any:
    """Recursively drop None values and convert Path objects to strings.

    TOML has no null type, so any None value would cause tomli_w to raise
    TypeError.  We strip None entries from dicts entirely and leave other
    types untouched.
    """
    if isinstance(value, dict):
        return {
            k: _clean_for_toml(v)
            for k, v in value.items()
            if v is not None
        }
    if isinstance(value, list):
        return [_clean_for_toml(v) for v in value if v is not None]
    if isinstance(value, Path):
        return str(value)
    return value


def reset_settings_cache() -> None:
    """Clear the cached settings (useful for testing)."""
    global _cached_settings
    _cached_settings = None
