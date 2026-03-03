"""Tests for the settings system."""

import tempfile
from pathlib import Path

from hivecore.config.settings import (
    HiveSettings,
    LLMSettings,
    MemorySettings,
    get_settings,
    reset_settings_cache,
    save_settings,
)


class TestHiveSettings:
    """Tests for the settings model."""

    def test_default_settings(self) -> None:
        settings = HiveSettings()
        assert settings.llm.model == "gpt-4o"
        assert settings.llm.provider == "litellm"
        assert settings.llm.temperature == 0.7
        assert settings.memory.backend == "sqlite"
        assert settings.web.port == 8088
        assert settings.scheduler.enabled is True

    def test_custom_llm_settings(self) -> None:
        settings = HiveSettings(
            llm=LLMSettings(model="claude-3-opus", provider="anthropic", temperature=0.5)
        )
        assert settings.llm.model == "claude-3-opus"
        assert settings.llm.provider == "anthropic"
        assert settings.llm.temperature == 0.5

    def test_memory_settings_defaults(self) -> None:
        settings = MemorySettings()
        assert settings.max_short_term_messages == 50
        assert settings.compaction_threshold == 4000
        assert settings.bm25_weight == 0.3
        assert settings.vector_weight == 0.7

    def test_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"

            # Save
            settings = HiveSettings()
            settings.llm.model = "test-model"
            save_settings(settings, config_path)

            assert config_path.exists()

            # Load
            reset_settings_cache()
            loaded = get_settings(config_path)
            assert loaded.llm.model == "test-model"

    def test_settings_cache(self) -> None:
        reset_settings_cache()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # Same cached instance

    def test_nested_settings(self) -> None:
        settings = HiveSettings()
        assert settings.channels.discord.enabled is False
        assert settings.channels.telegram.enabled is False
        assert settings.agent.max_iterations == 20
