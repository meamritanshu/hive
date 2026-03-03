"""Tests for Fix 1 — Skill Hardening.

Covers:
- SkillContext: to_env(), build() filtering (only declared secrets exposed)
- _validate_permission / SkillManifest.__post_init__ (invalid tokens rejected)
- parse_requirements_header() (comment parsing)
- ensure_requirements() (no-op on empty list, calls pip, raises on failure)
- Skill helpers: has_permission(), requires_*, required_secrets()
- SkillLoader._check_permissions() (global default and per-skill allow-list)
- SkillLoader._load_allowlist() (reads TOML file)
- SkillLoader._load_file_skill() (requirements merged into manifest deps)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from hivecore.skills.base import (
    VALID_PERMISSIONS,
    Skill,
    SkillContext,
    SkillManifest,
    _validate_permission,
    ensure_requirements,
    parse_requirements_header,
    skill,
)
from hivecore.skills.loader import SkillLoader


# ---------------------------------------------------------------------------
# _validate_permission
# ---------------------------------------------------------------------------

class TestValidatePermission:
    """Unit tests for the _validate_permission helper."""

    def test_known_tokens_are_valid(self) -> None:
        for perm in VALID_PERMISSIONS:
            assert _validate_permission(perm), f"Expected '{perm}' to be valid"

    def test_secrets_token_with_key_is_valid(self) -> None:
        assert _validate_permission("secrets:OPENAI_API_KEY") is True
        assert _validate_permission("secrets:MY_TOKEN") is True

    def test_bare_secrets_prefix_is_invalid(self) -> None:
        # "secrets:" with no key name must be rejected
        assert _validate_permission("secrets:") is False

    def test_unknown_token_is_invalid(self) -> None:
        assert _validate_permission("admin") is False
        assert _validate_permission("root") is False
        assert _validate_permission("") is False

    def test_case_sensitive(self) -> None:
        # Permission tokens are lowercase; uppercase variants are unknown
        assert _validate_permission("Network") is False
        assert _validate_permission("FILESYSTEM") is False


# ---------------------------------------------------------------------------
# SkillManifest.__post_init__ validation
# ---------------------------------------------------------------------------

class TestSkillManifestValidation:
    """SkillManifest rejects invalid permission tokens at construction time."""

    def test_valid_permissions_accepted(self) -> None:
        m = SkillManifest(
            name="my_skill",
            permissions=["network", "filesystem", "secrets:API_KEY"],
        )
        assert m.permissions == ["network", "filesystem", "secrets:API_KEY"]

    def test_invalid_permission_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="unknown permissions"):
            SkillManifest(name="bad", permissions=["admin"])

    def test_multiple_invalid_permissions_listed_in_error(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            SkillManifest(name="bad", permissions=["admin", "root"])
        msg = str(exc_info.value)
        assert "admin" in msg
        assert "root" in msg

    def test_empty_permissions_always_valid(self) -> None:
        m = SkillManifest(name="safe", permissions=[])
        assert m.permissions == []

    def test_all_valid_tokens_accepted(self) -> None:
        perms = list(VALID_PERMISSIONS) + ["secrets:MY_KEY"]
        m = SkillManifest(name="full", permissions=perms)
        assert set(m.permissions) == set(perms)


# ---------------------------------------------------------------------------
# SkillContext
# ---------------------------------------------------------------------------

class TestSkillContext:
    """Tests for SkillContext: filtering and env-var export."""

    def test_to_env_returns_secrets_as_env_vars(self) -> None:
        ctx = SkillContext(
            skill_name="demo",
            secrets={"OPENAI_API_KEY": "sk-test", "OTHER": "val"},
        )
        env = ctx.to_env()
        assert env["OPENAI_API_KEY"] == "sk-test"
        assert env["OTHER"] == "val"

    def test_to_env_empty_when_no_secrets(self) -> None:
        ctx = SkillContext(skill_name="demo")
        assert ctx.to_env() == {}

    def test_build_only_exposes_declared_secrets(self) -> None:
        """Skills only receive secrets they explicitly declared."""
        ctx = SkillContext.build(
            skill_name="demo",
            declared_permissions=["network", "secrets:API_KEY"],
            secrets_source={
                "API_KEY": "abc123",
                "OTHER_SECRET": "should-not-appear",
            },
        )
        assert "API_KEY" in ctx.secrets
        assert "OTHER_SECRET" not in ctx.secrets
        assert ctx.secrets["API_KEY"] == "abc123"

    def test_build_with_no_secret_permissions(self) -> None:
        """No secrets are exposed when no secrets: permissions declared."""
        ctx = SkillContext.build(
            skill_name="demo",
            declared_permissions=["network", "filesystem"],
            secrets_source={"SECRET": "value"},
        )
        assert ctx.secrets == {}

    def test_build_missing_secret_is_silently_omitted(self) -> None:
        """A declared secret that is absent from secrets_source is not included."""
        ctx = SkillContext.build(
            skill_name="demo",
            declared_permissions=["secrets:MISSING_KEY"],
            secrets_source={},
        )
        assert "MISSING_KEY" not in ctx.secrets

    def test_build_multiple_secrets(self) -> None:
        ctx = SkillContext.build(
            skill_name="multi",
            declared_permissions=["secrets:KEY_A", "secrets:KEY_B", "network"],
            secrets_source={"KEY_A": "aaa", "KEY_B": "bbb", "KEY_C": "ccc"},
        )
        assert ctx.secrets == {"KEY_A": "aaa", "KEY_B": "bbb"}


# ---------------------------------------------------------------------------
# parse_requirements_header
# ---------------------------------------------------------------------------

class TestParseRequirementsHeader:
    """Tests for the # Requirements: comment parser."""

    def test_single_requirement(self) -> None:
        src = "# Requirements: requests\nprint('hello')"
        assert parse_requirements_header(src) == ["requests"]

    def test_multiple_requirements(self) -> None:
        src = "# Requirements: requests>=2.31, beautifulsoup4\n"
        reqs = parse_requirements_header(src)
        assert reqs == ["requests>=2.31", "beautifulsoup4"]

    def test_case_insensitive_keyword(self) -> None:
        src = "# requirement: pandas\n"
        assert parse_requirements_header(src) == ["pandas"]

    def test_no_header_returns_empty_list(self) -> None:
        src = "print('no requirements here')\n"
        assert parse_requirements_header(src) == []

    def test_header_anywhere_in_file(self) -> None:
        src = "# Some preamble\n\n# Requirements: numpy\n\ndef foo(): pass\n"
        assert parse_requirements_header(src) == ["numpy"]

    def test_extra_whitespace_stripped(self) -> None:
        src = "#  Requirements :  scipy , sympy  \n"
        reqs = parse_requirements_header(src)
        assert reqs == ["scipy", "sympy"]

    def test_version_specifiers_preserved(self) -> None:
        src = "# Requirements: flask>=2.0,<3.0, sqlalchemy==2.0.1\n"
        reqs = parse_requirements_header(src)
        assert "flask>=2.0,<3.0" in reqs or any("flask" in r for r in reqs)

    def test_empty_after_colon_returns_empty(self) -> None:
        src = "# Requirements: \n"
        assert parse_requirements_header(src) == []


# ---------------------------------------------------------------------------
# ensure_requirements
# ---------------------------------------------------------------------------

class TestEnsureRequirements:
    """Tests for ensure_requirements()."""

    def test_no_op_on_empty_list(self) -> None:
        """Should return immediately without calling pip when list is empty."""
        with patch("subprocess.run") as mock_run:
            ensure_requirements([], skill_name="test_skill")
        mock_run.assert_not_called()

    def test_calls_pip_install(self) -> None:
        """Should invoke pip install for each requirement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            venv_path = Path(tmpdir) / "test_venv"
            # Pre-create the venv dir so venv.create is not called
            venv_path.mkdir()
            # Create a fake pip executable
            import sys
            if sys.platform == "win32":
                pip_path = venv_path / "Scripts"
                pip_path.mkdir(parents=True)
                (pip_path / "pip.exe").write_bytes(b"")
            else:
                pip_path = venv_path / "bin"
                pip_path.mkdir(parents=True)
                (pip_path / "pip").write_bytes(b"")

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ensure_requirements(
                    ["requests", "beautifulsoup4"],
                    skill_name="test_skill",
                    venv_dir=str(venv_path),
                )

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]  # first positional arg (the cmd list)
            assert "install" in call_args
            assert "requests" in call_args
            assert "beautifulsoup4" in call_args

    def test_raises_runtime_error_on_pip_failure(self) -> None:
        """Should raise RuntimeError when pip exits with non-zero status."""
        import subprocess

        with tempfile.TemporaryDirectory() as tmpdir:
            venv_path = Path(tmpdir) / "test_venv"
            venv_path.mkdir()
            import sys
            if sys.platform == "win32":
                pip_path = venv_path / "Scripts"
                pip_path.mkdir(parents=True)
                (pip_path / "pip.exe").write_bytes(b"")
            else:
                pip_path = venv_path / "bin"
                pip_path.mkdir(parents=True)
                (pip_path / "pip").write_bytes(b"")

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.CalledProcessError(
                    returncode=1,
                    cmd=["pip", "install"],
                    stderr="Could not find package",
                )
                with pytest.raises(RuntimeError, match="installation failed"):
                    ensure_requirements(
                        ["nonexistent-package-xyz"],
                        skill_name="test_skill",
                        venv_dir=str(venv_path),
                    )


# ---------------------------------------------------------------------------
# Skill permission helpers
# ---------------------------------------------------------------------------

class TestSkillPermissionHelpers:
    """Tests for Skill.has_permission(), requires_*, required_secrets()."""

    def _make_skill(self, permissions: list[str]) -> Skill:
        manifest = SkillManifest(name="demo", permissions=permissions)
        return Skill(manifest=manifest)

    def test_has_permission_true(self) -> None:
        s = self._make_skill(["network"])
        assert s.has_permission("network") is True

    def test_has_permission_false(self) -> None:
        s = self._make_skill(["network"])
        assert s.has_permission("filesystem") is False

    def test_requires_network(self) -> None:
        assert self._make_skill(["network"]).requires_network() is True
        assert self._make_skill([]).requires_network() is False

    def test_requires_filesystem(self) -> None:
        assert self._make_skill(["filesystem"]).requires_filesystem() is True
        assert self._make_skill(["network"]).requires_filesystem() is False

    def test_requires_shell(self) -> None:
        assert self._make_skill(["shell"]).requires_shell() is True
        assert self._make_skill([]).requires_shell() is False

    def test_required_secrets_extracted(self) -> None:
        s = self._make_skill(["network", "secrets:OPENAI_API_KEY", "secrets:MY_TOKEN"])
        secrets = s.required_secrets()
        assert "OPENAI_API_KEY" in secrets
        assert "MY_TOKEN" in secrets
        assert "network" not in secrets

    def test_required_secrets_empty_when_no_secrets(self) -> None:
        s = self._make_skill(["network", "filesystem"])
        assert s.required_secrets() == []


# ---------------------------------------------------------------------------
# SkillLoader._check_permissions
# ---------------------------------------------------------------------------

class TestSkillLoaderCheckPermissions:
    """Tests for SkillLoader._check_permissions() — global and per-skill allow-list."""

    def _make_skill(self, permissions: list[str]) -> Skill:
        manifest = SkillManifest(name="demo", permissions=permissions)
        return Skill(manifest=manifest)

    def test_all_permitted_returns_true(self) -> None:
        loader = SkillLoader(allowed_permissions=frozenset(["network"]))
        s = self._make_skill(["network"])
        assert loader._check_permissions(s, allow_list=None) is True

    def test_denied_permission_returns_false(self) -> None:
        loader = SkillLoader(allowed_permissions=frozenset())
        s = self._make_skill(["network"])
        assert loader._check_permissions(s, allow_list=None) is False

    def test_per_skill_allowlist_overrides_global(self) -> None:
        """A per-skill allow-list takes precedence over the global default."""
        # Global denies network; per-skill allows it
        loader = SkillLoader(allowed_permissions=frozenset())
        s = self._make_skill(["network"])
        assert loader._check_permissions(s, allow_list=frozenset(["network"])) is True

    def test_per_skill_allowlist_can_deny_globally_allowed(self) -> None:
        """Per-skill allow-list can be more restrictive than global."""
        loader = SkillLoader(allowed_permissions=frozenset(["network", "filesystem"]))
        s = self._make_skill(["filesystem"])
        # Per-skill list doesn't include filesystem
        assert loader._check_permissions(s, allow_list=frozenset(["network"])) is False

    def test_no_permissions_declared_always_passes(self) -> None:
        loader = SkillLoader(allowed_permissions=frozenset())
        s = self._make_skill([])
        assert loader._check_permissions(s, allow_list=None) is True

    def test_partial_denied_still_fails(self) -> None:
        loader = SkillLoader(allowed_permissions=frozenset(["network"]))
        s = self._make_skill(["network", "filesystem"])
        assert loader._check_permissions(s, allow_list=None) is False


# ---------------------------------------------------------------------------
# SkillLoader._load_allowlist
# ---------------------------------------------------------------------------

class TestSkillLoaderLoadAllowlist:
    """Tests for SkillLoader._load_allowlist()."""

    def test_returns_none_when_no_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = SkillLoader()
            result = loader._load_allowlist(Path(tmpdir), "nonexistent_skill")
        assert result is None

    def test_reads_permissions_from_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            toml_content = '[permissions]\nallowed = ["network", "secrets:API_KEY"]\n'
            (Path(tmpdir) / "my_skill.toml").write_text(toml_content, encoding="utf-8")
            loader = SkillLoader()
            result = loader._load_allowlist(Path(tmpdir), "my_skill")
        assert result is not None
        assert "network" in result
        assert "secrets:API_KEY" in result

    def test_returns_none_on_malformed_toml(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "broken.toml").write_text("not valid toml ][", encoding="utf-8")
            loader = SkillLoader()
            result = loader._load_allowlist(Path(tmpdir), "broken")
        assert result is None

    def test_empty_allowed_list_returns_empty_frozenset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            toml_content = "[permissions]\nallowed = []\n"
            (Path(tmpdir) / "safe_skill.toml").write_text(toml_content, encoding="utf-8")
            loader = SkillLoader()
            result = loader._load_allowlist(Path(tmpdir), "safe_skill")
        assert result == frozenset()


# ---------------------------------------------------------------------------
# SkillLoader._load_file_skill — requirements merged into manifest
# ---------------------------------------------------------------------------

class TestSkillLoaderRequirementsIntegration:
    """Requirements parsed from # Requirements: header are merged into manifest deps."""

    async def test_requirements_merged_into_manifest_dependencies(self) -> None:
        """After loading, the skill's manifest.dependencies includes header reqs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_src = (
                "# Requirements: requests\n"
                "from hivecore.skills.base import skill\n\n"
                "@skill(name='web_fetch', permissions=['network'])\n"
                "def web_fetch(url: str) -> str:\n"
                "    return url\n"
            )
            skill_file = Path(tmpdir) / "web_fetch.py"
            skill_file.write_text(skill_src, encoding="utf-8")

            loader = SkillLoader(
                skill_dirs=[Path(tmpdir)],
                allowed_permissions=frozenset(["network"]),
                install_requirements=False,  # Don't actually run pip
            )
            skills = await loader.load_all()

        assert len(skills) == 1
        assert "requests" in skills[0].manifest.dependencies

    async def test_skill_with_denied_permission_is_not_loaded(self) -> None:
        """Skills whose permissions exceed the allow-list are silently skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_src = (
                "from hivecore.skills.base import skill\n\n"
                "@skill(name='dangerous', permissions=['shell'])\n"
                "def run_shell(cmd: str) -> str:\n"
                "    return cmd\n"
            )
            skill_file = Path(tmpdir) / "dangerous.py"
            skill_file.write_text(skill_src, encoding="utf-8")

            # Loader's global default does NOT allow 'shell'
            loader = SkillLoader(
                skill_dirs=[Path(tmpdir)],
                allowed_permissions=frozenset(["network"]),
                install_requirements=False,
            )
            skills = await loader.load_all()

        assert skills == []

    async def test_skill_with_per_skill_allowlist_is_loaded(self) -> None:
        """A per-skill .toml allow-list can grant permissions denied by global default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_src = (
                "from hivecore.skills.base import skill\n\n"
                "@skill(name='net_skill', permissions=['network'])\n"
                "def net_skill(url: str) -> str:\n"
                "    return url\n"
            )
            skill_file = Path(tmpdir) / "net_skill.py"
            skill_file.write_text(skill_src, encoding="utf-8")

            # Write a per-skill allow-list granting 'network'
            toml_content = '[permissions]\nallowed = ["network"]\n'
            (Path(tmpdir) / "net_skill.toml").write_text(toml_content, encoding="utf-8")

            # Global default is empty (deny all)
            loader = SkillLoader(
                skill_dirs=[Path(tmpdir)],
                allowed_permissions=frozenset(),
                install_requirements=False,
            )
            skills = await loader.load_all()

        assert len(skills) == 1
        assert skills[0].name == "net_skill"


# ---------------------------------------------------------------------------
# @skill decorator — permission validation at decoration time
# ---------------------------------------------------------------------------

class TestSkillDecoratorPermissions:
    """The @skill decorator raises ValueError for invalid permission tokens."""

    def test_valid_permissions_accepted(self) -> None:
        @skill(name="good", permissions=["network"])
        def func(x: str) -> str:
            return x

        assert func.permissions == ["network"]

    def test_invalid_permission_raises_at_decoration_time(self) -> None:
        with pytest.raises(ValueError, match="unknown permissions"):
            @skill(name="bad", permissions=["superuser"])
            def func(x: str) -> str:
                return x

    def test_no_permissions_decorator(self) -> None:
        @skill(name="safe_func")
        def func(x: str) -> str:
            return x

        assert func.permissions == []
