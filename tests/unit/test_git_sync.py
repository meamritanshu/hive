"""Unit tests for MemoryGitSync — Fix 4: git-integrated memory."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivecore.memory.git_sync import MemoryGitSync, _GITIGNORE_CONTENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_is_available() -> bool:
    """Return True if git is on PATH (used to skip tests in bare envs)."""
    try:
        result = subprocess.run(
            ["git", "--version"], capture_output=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


# ---------------------------------------------------------------------------
# Tests: initialization
# ---------------------------------------------------------------------------

class TestMemoryGitSyncInit:
    """Tests for MemoryGitSync.initialize()."""

    async def test_creates_git_repo(self, tmp_dir: Path) -> None:
        """initialize() should run git init in the data directory."""
        if not _git_is_available():
            pytest.skip("git not available in this environment")

        sync = MemoryGitSync(tmp_dir)
        await sync.initialize()

        assert (tmp_dir / ".git").exists(), ".git directory should be created"

    async def test_writes_gitignore(self, tmp_dir: Path) -> None:
        """initialize() should write a .gitignore file."""
        if not _git_is_available():
            pytest.skip("git not available in this environment")

        sync = MemoryGitSync(tmp_dir)
        await sync.initialize()

        gitignore = tmp_dir / ".gitignore"
        assert gitignore.exists(), ".gitignore should be created"
        content = gitignore.read_text(encoding="utf-8")
        # Must exclude the binary artefacts
        assert "vectors.db" in content
        assert "shadow.duckdb" in content
        assert "skill_envs/" in content

    async def test_idempotent_on_existing_repo(self, tmp_dir: Path) -> None:
        """Calling initialize() twice should not raise."""
        if not _git_is_available():
            pytest.skip("git not available in this environment")

        sync = MemoryGitSync(tmp_dir)
        await sync.initialize()
        await sync.initialize()  # second call — must be safe
        assert (tmp_dir / ".git").exists()

    async def test_no_git_graceful(self, tmp_dir: Path) -> None:
        """If git is not on PATH, initialize() should log a warning and return
        without raising."""
        sync = MemoryGitSync(tmp_dir)
        # Simulate git being absent by patching the availability check
        with patch.object(sync, "_git_available_check", AsyncMock(return_value=False)):
            await sync.initialize()  # must not raise
        # .git should NOT exist because git was "unavailable"
        assert not (tmp_dir / ".git").exists()


# ---------------------------------------------------------------------------
# Tests: commit
# ---------------------------------------------------------------------------

class TestMemoryGitSyncCommit:
    """Tests for MemoryGitSync.commit()."""

    async def test_commit_creates_git_commit(self, tmp_dir: Path) -> None:
        """After storing a file, commit() should create a git commit."""
        if not _git_is_available():
            pytest.skip("git not available in this environment")

        sync = MemoryGitSync(tmp_dir)
        await sync.initialize()

        # Configure git identity for the test (needed in CI / minimal envs)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_dir)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir)

        # Write a file to commit
        (tmp_dir / "memory.md").write_text("## Memory\n", encoding="utf-8")

        committed = await sync.commit("test: initial memory commit")
        assert committed is True

        # Verify the commit exists
        result = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=tmp_dir,
            capture_output=True,
            text=True,
        )
        assert "test: initial memory commit" in result.stdout

    async def test_commit_returns_false_when_nothing_changed(self, tmp_dir: Path) -> None:
        """commit() returns False when there are no staged changes."""
        if not _git_is_available():
            pytest.skip("git not available in this environment")

        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_dir)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir)

        sync = MemoryGitSync(tmp_dir)
        await sync.initialize()

        # First commit — stages the .gitignore
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_dir)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir)
        await sync.commit("initial")

        # No further changes — commit should return False
        result = await sync.commit("empty commit")
        assert result is False

    async def test_commit_unavailable_git_returns_false(self, tmp_dir: Path) -> None:
        """commit() returns False when git is unavailable."""
        sync = MemoryGitSync(tmp_dir)
        with patch.object(sync, "_git_available_check", AsyncMock(return_value=False)):
            result = await sync.commit("should not commit")
        assert result is False


# ---------------------------------------------------------------------------
# Tests: gitignore content
# ---------------------------------------------------------------------------

class TestGitignoreContent:
    """Verify the built-in .gitignore excludes the right artefacts."""

    def test_excludes_vectors_db(self) -> None:
        assert "vectors.db" in _GITIGNORE_CONTENT

    def test_excludes_shadow_duckdb(self) -> None:
        assert "shadow.duckdb" in _GITIGNORE_CONTENT

    def test_excludes_skill_envs(self) -> None:
        assert "skill_envs/" in _GITIGNORE_CONTENT

    def test_excludes_pycache(self) -> None:
        assert "__pycache__/" in _GITIGNORE_CONTENT


# ---------------------------------------------------------------------------
# Tests: push / pull passthrough
# ---------------------------------------------------------------------------

class TestMemoryGitSyncPushPull:
    """push() and pull() should return False gracefully when git is absent."""

    async def test_push_returns_false_no_git(self, tmp_dir: Path) -> None:
        sync = MemoryGitSync(tmp_dir)
        with patch.object(sync, "_git_available_check", AsyncMock(return_value=False)):
            assert await sync.push() is False

    async def test_pull_returns_false_no_git(self, tmp_dir: Path) -> None:
        sync = MemoryGitSync(tmp_dir)
        with patch.object(sync, "_git_available_check", AsyncMock(return_value=False)):
            assert await sync.pull() is False
