"""Execution provider factory.

Returns the appropriate :class:`ExecutionProvider` based on
``settings.skills.sandbox_type``.

Supported values
----------------
``"subprocess"`` (default)
    Uses :class:`SubprocessSandbox` — a plain Python subprocess.
    No extra dependencies required.

``"docker"``
    Uses :class:`DockerProvider` — runs code inside a throwaway Docker
    container.  Falls back to ``subprocess`` automatically if Docker is
    unavailable.
"""

from __future__ import annotations

import logging

from hivecore.runtime.sandbox.base import ExecutionProvider

logger = logging.getLogger(__name__)


def get_execution_provider(
    sandbox_type: str = "subprocess",
    timeout: int = 300,
    max_memory_mb: int = 512,
) -> ExecutionProvider:
    """Return the execution provider for the given *sandbox_type*.

    Args:
        sandbox_type: One of ``"subprocess"`` or ``"docker"``.
            Unknown values fall back to ``"subprocess"`` with a warning.
        timeout: Execution timeout in seconds passed to the provider.
        max_memory_mb: Memory limit passed to the provider (Docker only).

    Returns:
        A ready-to-use :class:`ExecutionProvider` instance.
    """
    sandbox_type = sandbox_type.lower().strip()

    if sandbox_type == "docker":
        try:
            from hivecore.runtime.sandbox.docker_provider import DockerProvider
            logger.debug("Execution provider: DockerProvider (image=python:3.11-slim)")
            return DockerProvider(timeout=timeout, max_memory_mb=max_memory_mb)
        except ImportError as e:
            logger.warning(
                "DockerProvider unavailable (%s) — falling back to SubprocessSandbox", e
            )

    if sandbox_type not in ("subprocess", "docker"):
        logger.warning(
            "Unknown sandbox_type %r — defaulting to 'subprocess'", sandbox_type
        )

    from hivecore.runtime.sandbox.subprocess import SubprocessSandbox
    logger.debug("Execution provider: SubprocessSandbox")
    return SubprocessSandbox(timeout=timeout, max_memory_mb=max_memory_mb)
