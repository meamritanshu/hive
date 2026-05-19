"""Docker-based execution provider.

Runs skill code inside a fresh ``docker run --rm`` container for strong
isolation.  Falls back to :class:`SubprocessSandbox` automatically if:

- The ``docker`` CLI is not found on ``PATH``
- The Docker daemon is unreachable
- Any error occurs during container startup

Enable via ``settings.skills.sandbox_type = "docker"``.

Security properties
-------------------
- Each call gets a brand-new throwaway container (``--rm``).
- Network access is blocked by default (``--network none``).
  If the skill declares ``permission:network``, the flag is omitted.
- Memory capped at ``max_memory_mb`` (default 256 MB).
- CPU limited to 1 core by default.
- The container is always killed after ``timeout`` seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging
import textwrap
from pathlib import Path
from typing import Any

from hivecore.runtime.sandbox.base import ExecutionProvider

logger = logging.getLogger(__name__)

# Docker image used for sandboxed execution.  Users may override by
# subclassing or by setting ``HIVECORE_DOCKER_IMAGE`` in the environment.
DEFAULT_IMAGE = "python:3.11-slim"


class DockerProvider(ExecutionProvider):
    """Sandboxed execution inside a Docker container.

    Implements :class:`ExecutionProvider` using ``docker run --rm``.
    Automatically falls back to :class:`SubprocessSandbox` if Docker is
    unavailable so the agent degrades gracefully.

    Args:
        image: Docker image to use (default: ``python:3.11-slim``).
        timeout: Execution timeout in seconds (default: 300).
        max_memory_mb: Container memory limit in MB (default: 256).
        allow_network: Allow outbound network access (default: False).
        working_dir: Host directory to bind-mount as the container working
            directory (optional).
    """

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        timeout: int = 300,
        max_memory_mb: int = 256,
        allow_network: bool = False,
        working_dir: Path | None = None,
    ) -> None:
        self.image = image
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.allow_network = allow_network
        self.working_dir = working_dir
        self._docker_available: bool | None = None
        self._fallback: ExecutionProvider | None = None

    # ------------------------------------------------------------------
    # ExecutionProvider interface
    # ------------------------------------------------------------------

    async def execute_function(
        self,
        func_module: str,
        func_name: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a named function inside a Docker container.

        Falls back to :class:`SubprocessSandbox` if Docker is unavailable.
        """
        if not await self._docker_available_check():
            return await (await self._get_fallback()).execute_function(
                func_module, func_name, kwargs
            )

        script = textwrap.dedent(f"""
        import json, sys, importlib, asyncio, inspect

        try:
            module = importlib.import_module({func_module!r})
            func = getattr(module, {func_name!r})
            kwargs = json.loads({json.dumps(json.dumps(kwargs))})
            if inspect.iscoroutinefunction(func):
                result = asyncio.run(func(**kwargs))
            else:
                result = func(**kwargs)
            print(json.dumps({{"success": True, "result": str(result)}}))
        except Exception as e:
            print(json.dumps({{"success": False, "error": str(e), "type": type(e).__name__}}))
        """)

        return await self._run_in_container(script, mode="function")

    async def execute_code(self, code: str) -> dict[str, Any]:
        """Execute arbitrary Python code inside a Docker container.

        Falls back to :class:`SubprocessSandbox` if Docker is unavailable.
        """
        if not await self._docker_available_check():
            return await (await self._get_fallback()).execute_code(code)

        return await self._run_in_container(code, mode="code")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run_in_container(
        self, code: str, mode: str = "code"
    ) -> dict[str, Any]:
        """Run *code* inside a fresh ``docker run --rm`` container."""
        docker_args = self._build_docker_args(code)
        process: asyncio.subprocess.Process | None = None

        try:
            process = await asyncio.create_subprocess_exec(
                *docker_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_b, stderr_b = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            stdout = stdout_b.decode("utf-8", errors="replace").strip()
            stderr = stderr_b.decode("utf-8", errors="replace").strip()

            if mode == "function":
                try:
                    result = json.loads(stdout.split("\n")[-1])
                except (json.JSONDecodeError, IndexError):
                    result = {"success": False, "error": "Failed to parse output", "raw": stdout}
                return {
                    "result": result,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": process.returncode,
                }
            else:
                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": process.returncode,
                }

        except asyncio.TimeoutError:
            logger.error("Docker execution timed out after %ds — killing container", self.timeout)
            if process is not None:
                process.kill()
            error_payload = {"success": False, "error": f"Execution timed out after {self.timeout}s"}
            return {
                "result": error_payload,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            } if mode == "function" else {
                "stdout": "",
                "stderr": f"Execution timed out after {self.timeout}s",
                "exit_code": -1,
            }
        except Exception as e:
            logger.error("DockerProvider execution error: %s — falling back to subprocess", e)
            fallback = await self._get_fallback()
            if mode == "function":
                # We don't have func_module/func_name here, so surface the error
                return {
                    "result": {"success": False, "error": str(e)},
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                }
            return await fallback.execute_code(code)

    def _build_docker_args(self, code: str) -> list[str]:
        """Build the ``docker run`` command-line arguments."""
        args = [
            "docker", "run", "--rm",
            "--memory", f"{self.max_memory_mb}m",
            "--cpus", "1",
        ]

        if not self.allow_network:
            args += ["--network", "none"]

        if self.working_dir:
            args += ["-v", f"{self.working_dir}:/workdir", "-w", "/workdir"]

        # Pass the code via stdin to avoid shell-escaping headaches
        args += [
            self.image,
            "python", "-c", code,
        ]
        return args

    async def _docker_available_check(self) -> bool:
        """Return ``True`` if ``docker`` is on PATH and the daemon responds."""
        if self._docker_available is not None:
            return self._docker_available

        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.wait(), timeout=5)
            self._docker_available = proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError):
            self._docker_available = False

        if not self._docker_available:
            logger.info(
                "Docker not available — DockerProvider will fall back to SubprocessSandbox"
            )

        return self._docker_available  # type: ignore[return-value]

    async def _get_fallback(self) -> ExecutionProvider:
        """Lazily create the subprocess fallback provider."""
        if self._fallback is None:
            from hivecore.runtime.sandbox.subprocess import SubprocessSandbox
            self._fallback = SubprocessSandbox(
                timeout=self.timeout,
                working_dir=self.working_dir,
            )
        return self._fallback
