"""Git-integrated memory synchronisation.

Keeps ``~/.hivecore/`` under version control so that memory compaction
events are recorded as auditable, diffable commits.  Optionally supports
push/pull to a user-configured remote for cross-device sync.

Usage::

    from hivecore.memory.git_sync import MemoryGitSync

    sync = MemoryGitSync(data_dir)
    await sync.initialize()
    await sync.commit("chore: weekly compaction 2026-W09")
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths inside the data directory that should never be committed
# (binary / generated artefacts that are rebuilt on startup).
_GITIGNORE_CONTENT = """\
# HiveCore — auto-generated .gitignore
# Binary / ephemeral artefacts — excluded from version control
vectors.db
vectors.db-wal
vectors.db-shm
shadow.duckdb
skill_envs/
__pycache__/
*.pyc
"""


class MemoryGitSync:
    """Manages a git repository rooted at *data_dir*.

    All git operations run in a subprocess so they never block the event loop.

    Args:
        data_dir: Path to the HiveCore data directory (e.g. ``~/.hivecore/``).
        auto_push: If ``True``, attempt ``git push`` after every commit.
            Defaults to ``False`` — the user must opt in explicitly.
    """

    def __init__(self, data_dir: Path, auto_push: bool = False) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.auto_push = auto_push
        self._git_available: bool | None = None  # None = not checked yet

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Ensure *data_dir* is a git repository.

        If it is not already a repo, runs ``git init`` and creates a
        ``.gitignore`` with sensible defaults.  Safe to call multiple
        times (idempotent).
        """
        if not await self._git_available_check():
            logger.warning(
                "git not found on PATH — MemoryGitSync is disabled. "
                "Install git to enable memory versioning."
            )
            return

        git_dir = self.data_dir / ".git"
        if not git_dir.exists():
            await self._run("git", "init", cwd=self.data_dir)
            logger.info("Initialised git repository at %s", self.data_dir)

        # Write / update .gitignore (idempotent — overwrite is fine)
        gitignore_path = self.data_dir / ".gitignore"
        gitignore_path.write_text(_GITIGNORE_CONTENT, encoding="utf-8")

        # Stage the .gitignore so the very first commit is meaningful
        await self._run("git", "add", ".gitignore", cwd=self.data_dir)

    async def commit(self, message: str) -> bool:
        """Stage all changes under *data_dir* and create a commit.

        Binary / generated files listed in ``.gitignore`` are excluded
        automatically.

        Args:
            message: Commit message (e.g. ``"chore: weekly compaction 2026-W09"``).

        Returns:
            ``True`` if a commit was created, ``False`` if there was nothing
            to commit or git is unavailable.
        """
        if not await self._git_available_check():
            return False

        # Stage everything (respects .gitignore)
        await self._run("git", "add", "--all", cwd=self.data_dir)

        # Check if there is anything staged
        returncode, stdout, _ = await self._run(
            "git", "diff", "--cached", "--quiet", cwd=self.data_dir, check=False
        )
        if returncode == 0:
            # Exit code 0 means no diff — nothing to commit
            logger.debug("MemoryGitSync: nothing to commit")
            return False

        # Commit
        returncode, _, stderr = await self._run(
            "git", "commit", "-m", message, cwd=self.data_dir, check=False
        )
        if returncode != 0:
            logger.warning("MemoryGitSync commit failed: %s", stderr.strip())
            return False

        logger.info("MemoryGitSync committed: %s", message)

        if self.auto_push:
            await self.push()

        return True

    async def push(self) -> bool:
        """Push the current branch to its configured upstream.

        Returns:
            ``True`` on success, ``False`` on failure or if git is unavailable.
        """
        if not await self._git_available_check():
            return False

        returncode, _, stderr = await self._run(
            "git", "push", cwd=self.data_dir, check=False
        )
        if returncode != 0:
            logger.warning("MemoryGitSync push failed: %s", stderr.strip())
            return False

        logger.info("MemoryGitSync pushed successfully")
        return True

    async def pull(self) -> bool:
        """Pull from the configured upstream.

        Returns:
            ``True`` on success, ``False`` on failure or if git is unavailable.
        """
        if not await self._git_available_check():
            return False

        returncode, _, stderr = await self._run(
            "git", "pull", cwd=self.data_dir, check=False
        )
        if returncode != 0:
            logger.warning("MemoryGitSync pull failed: %s", stderr.strip())
            return False

        logger.info("MemoryGitSync pulled successfully")
        return True

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _git_available_check(self) -> bool:
        """Return ``True`` if ``git`` is on PATH (cached after first check)."""
        if self._git_available is not None:
            return self._git_available

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "--version",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            self._git_available = proc.returncode == 0
        except FileNotFoundError:
            self._git_available = False

        return self._git_available  # type: ignore[return-value]

    async def _run(
        self,
        *args: str,
        cwd: Path,
        check: bool = True,
    ) -> tuple[int, str, str]:
        """Run a git subprocess and return (returncode, stdout, stderr).

        Args:
            *args: Command and arguments.
            cwd: Working directory.
            check: If ``True`` (default), log a warning on non-zero exit.

        Returns:
            Tuple of (returncode, stdout_text, stderr_text).
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout_b, stderr_b = await proc.communicate()
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")

            if check and proc.returncode != 0:
                logger.warning(
                    "git command %r exited %d: %s",
                    args, proc.returncode, stderr.strip(),
                )

            return proc.returncode, stdout, stderr

        except Exception as exc:
            logger.error("Failed to run git command %r: %s", args, exc)
            return -1, "", str(exc)
