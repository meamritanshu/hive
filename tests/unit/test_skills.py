"""Tests for the skill system."""

import tempfile
from pathlib import Path

import pytest

from hivecore.skills.base import Skill, SkillManifest, skill
from hivecore.skills.loader import SkillLoader
from hivecore.skills.registry import SkillRegistry


class TestSkillDecorator:
    """Tests for the @skill decorator."""

    def test_skill_decorator_creates_skill(self) -> None:
        @skill(name="test_skill", description="A test skill")
        def my_skill(arg: str) -> str:
            return arg

        assert isinstance(my_skill, Skill)
        assert my_skill.name == "test_skill"
        assert my_skill.description == "A test skill"

    def test_skill_has_tools(self) -> None:
        @skill(name="echo", description="Echo input")
        def echo(text: str) -> str:
            return text

        tools = echo.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "echo"

    def test_skill_metadata(self) -> None:
        @skill(
            name="weather",
            description="Get weather",
            version="1.0.0",
            author="Test Author",
            tags=["weather", "api"],
        )
        def get_weather(city: str) -> str:
            return f"Sunny in {city}"

        assert get_weather.version == "1.0.0"
        assert get_weather.author == "Test Author"
        assert "weather" in get_weather.manifest.tags


class TestSkillManifest:
    """Tests for SkillManifest."""

    def test_default_manifest(self) -> None:
        manifest = SkillManifest(name="test")
        assert manifest.name == "test"
        assert manifest.version == "0.1.0"
        assert manifest.author == "unknown"
        assert manifest.dependencies == []

    def test_full_manifest(self) -> None:
        manifest = SkillManifest(
            name="web_scraper",
            description="Scrapes web pages",
            version="2.0.0",
            author="DevTeam",
            dependencies=["beautifulsoup4", "httpx"],
            permissions=["network"],
            tags=["web", "scraping"],
        )
        assert manifest.dependencies == ["beautifulsoup4", "httpx"]
        assert "network" in manifest.permissions


class TestSkillRegistry:
    """Tests for SkillRegistry."""

    def test_register_and_get(self) -> None:
        registry = SkillRegistry()

        @skill(name="test", description="Test")
        def test_func(x: str) -> str:
            return x

        registry.register(test_func)
        assert registry.get("test") is test_func
        assert "test" in registry

    def test_list_all(self) -> None:
        registry = SkillRegistry()

        for i in range(3):
            @skill(name=f"skill_{i}", description=f"Skill {i}")
            def func(x: str) -> str:
                return x
            registry.register(func)

        all_skills = registry.list_all()
        assert len(all_skills) == 3

    def test_unregister(self) -> None:
        registry = SkillRegistry()

        @skill(name="removable", description="Removable")
        def func(x: str) -> str:
            return x

        registry.register(func)
        assert registry.unregister("removable") is True
        assert "removable" not in registry


class TestSkillLoader:
    """Tests for SkillLoader."""

    @pytest.mark.asyncio
    async def test_load_from_empty_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SkillLoader([Path(tmpdir)])
            skills = await loader.load_all()
            assert skills == []

    @pytest.mark.asyncio
    async def test_load_file_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_file = Path(tmpdir) / "my_skill.py"
            skill_file.write_text(
                'from hivecore.skills.base import skill\n\n'
                '@skill(name="loaded_skill", description="A loaded skill")\n'
                'def loaded_skill(x: str) -> str:\n'
                '    return x.upper()\n',
                encoding="utf-8",
            )

            loader = SkillLoader([Path(tmpdir)])
            skills = await loader.load_all()
            assert len(skills) == 1
            assert skills[0].name == "loaded_skill"

    @pytest.mark.asyncio
    async def test_skip_underscore_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "__init__.py").write_text("", encoding="utf-8")
            (Path(tmpdir) / "_private.py").write_text("x = 1", encoding="utf-8")

            loader = SkillLoader([Path(tmpdir)])
            skills = await loader.load_all()
            assert skills == []
