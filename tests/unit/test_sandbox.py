"""Unit tests for Fix 5: ExecutionProvider pattern.

Covers:
- ExecutionProvider abstract interface
- SubprocessSandbox (implements ExecutionProvider)
- DockerProvider (graceful fallback when Docker absent)
- factory.get_execution_provider()
- Executor integration with the factory
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivecore.runtime.sandbox.base import ExecutionProvider
from hivecore.runtime.sandbox.subprocess import SubprocessProvider, SubprocessSandbox
from hivecore.runtime.sandbox.factory import get_execution_provider


# ---------------------------------------------------------------------------
# ExecutionProvider interface
# ---------------------------------------------------------------------------

class TestExecutionProviderInterface:
    """Verify the abstract base class cannot be instantiated directly."""

    def test_cannot_instantiate_abstract(self) -> None:
        with pytest.raises(TypeError):
            ExecutionProvider()  # type: ignore[abstract]

    def test_subprocess_sandbox_is_provider(self) -> None:
        assert issubclass(SubprocessSandbox, ExecutionProvider)

    def test_subprocess_provider_alias(self) -> None:
        """SubprocessProvider is an alias for SubprocessSandbox."""
        assert SubprocessProvider is SubprocessSandbox


# ---------------------------------------------------------------------------
# SubprocessSandbox
# ---------------------------------------------------------------------------

class TestSubprocessSandbox:
    """Tests for SubprocessSandbox.execute_code() and execute_function()."""

    async def test_execute_code_simple(self) -> None:
        sandbox = SubprocessSandbox(timeout=30)
        result = await sandbox.execute_code("print('hello')")
        assert result["exit_code"] == 0
        assert result["stdout"] == "hello"
        assert result["stderr"] == ""

    async def test_execute_code_stderr(self) -> None:
        sandbox = SubprocessSandbox(timeout=30)
        result = await sandbox.execute_code("import sys; sys.stderr.write('err')")
        assert result["exit_code"] == 0
        assert "err" in result["stderr"]

    async def test_execute_code_syntax_error(self) -> None:
        sandbox = SubprocessSandbox(timeout=30)
        result = await sandbox.execute_code("def broken(")
        assert result["exit_code"] != 0

    async def test_execute_code_timeout(self) -> None:
        """A code snippet that sleeps past the timeout should return exit_code -1."""
        sandbox = SubprocessSandbox(timeout=1)
        result = await sandbox.execute_code("import time; time.sleep(60)")
        assert result["exit_code"] == -1
        assert "timed out" in result["stderr"].lower()

    async def test_execute_function_success(self) -> None:
        """execute_function should run a module function and return its result."""
        sandbox = SubprocessSandbox(timeout=30)
        # Use a stdlib module as the target (json.dumps)
        result = await sandbox.execute_function(
            func_module="json",
            func_name="dumps",
            kwargs={"obj": {"key": "value"}},
        )
        assert result["exit_code"] == 0
        assert result["result"]["success"] is True
        assert "key" in result["result"]["result"]

    async def test_execute_function_unknown_module(self) -> None:
        """execute_function with a non-existent module should report error gracefully."""
        sandbox = SubprocessSandbox(timeout=30)
        result = await sandbox.execute_function(
            func_module="hivecore.__nonexistent_module__",
            func_name="noop",
            kwargs={},
        )
        assert result["result"]["success"] is False
        assert "error" in result["result"]

    async def test_process_variable_fixed_for_timeout(self) -> None:
        """Regression: process variable must be defined before the TimeoutError
        branch runs (fixes the latent bug noted in discovery notes)."""
        # If the process was never assigned (create_subprocess_exec raises),
        # the TimeoutError handler should not NameError on `process`.
        sandbox = SubprocessSandbox(timeout=30)
        with patch(
            "hivecore.runtime.sandbox.subprocess.asyncio.create_subprocess_exec",
            side_effect=OSError("no such file"),
        ):
            result = await sandbox.execute_code("print('x')")
        # Should return a failure dict, not raise NameError
        assert result["exit_code"] == -1


# ---------------------------------------------------------------------------
# DockerProvider (offline — Docker not required)
# ---------------------------------------------------------------------------

class TestDockerProviderFallback:
    """DockerProvider must fall back to SubprocessSandbox when Docker is absent."""

    async def test_falls_back_when_docker_unavailable(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider(timeout=30)
        # Force Docker to appear unavailable
        with patch.object(provider, "_docker_available_check", AsyncMock(return_value=False)):
            result = await provider.execute_code("print('fallback')")
        assert result["exit_code"] == 0
        assert result["stdout"] == "fallback"

    async def test_execute_function_fallback(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider(timeout=30)
        with patch.object(provider, "_docker_available_check", AsyncMock(return_value=False)):
            result = await provider.execute_function(
                func_module="json",
                func_name="dumps",
                kwargs={"obj": [1, 2, 3]},
            )
        assert result["result"]["success"] is True

    def test_docker_args_no_network_by_default(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider(allow_network=False)
        args = provider._build_docker_args("print('x')")
        assert "--network" in args
        assert "none" in args

    def test_docker_args_network_allowed(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider(allow_network=True)
        args = provider._build_docker_args("print('x')")
        assert "--network" not in args

    def test_docker_args_memory_limit(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider(max_memory_mb=128)
        args = provider._build_docker_args("print('x')")
        assert "--memory" in args
        assert "128m" in args

    def test_docker_args_includes_image(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider, DEFAULT_IMAGE

        provider = DockerProvider()
        args = provider._build_docker_args("print('x')")
        assert DEFAULT_IMAGE in args

    async def test_availability_cached(self) -> None:
        """_docker_available_check() result is cached after first call."""
        from hivecore.runtime.sandbox.docker_provider import DockerProvider

        provider = DockerProvider()
        with patch.object(provider, "_docker_available", False):
            # Already cached as False — should not spawn a subprocess
            result = await provider._docker_available_check()
            assert result is False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestGetExecutionProvider:
    """Tests for get_execution_provider() factory function."""

    def test_default_returns_subprocess(self) -> None:
        provider = get_execution_provider("subprocess")
        assert isinstance(provider, SubprocessSandbox)

    def test_unknown_type_falls_back_to_subprocess(self) -> None:
        provider = get_execution_provider("nonexistent_sandbox")
        assert isinstance(provider, SubprocessSandbox)

    def test_docker_type_returns_docker_provider(self) -> None:
        from hivecore.runtime.sandbox.docker_provider import DockerProvider
        provider = get_execution_provider("docker")
        assert isinstance(provider, DockerProvider)

    def test_case_insensitive(self) -> None:
        provider = get_execution_provider("SUBPROCESS")
        assert isinstance(provider, SubprocessSandbox)

    def test_timeout_passed_through(self) -> None:
        provider = get_execution_provider("subprocess", timeout=42)
        assert provider.timeout == 42  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Executor integration
# ---------------------------------------------------------------------------

class TestExecutorUsesProvider:
    """Executor should use the factory-supplied provider, not a hard-coded class."""

    def test_executor_default_is_subprocess(self) -> None:
        from hivecore.runtime.executor import Executor
        ex = Executor()
        assert isinstance(ex._provider, SubprocessSandbox)

    def test_executor_accepts_docker_sandbox_type(self) -> None:
        from hivecore.runtime.executor import Executor
        from hivecore.runtime.sandbox.docker_provider import DockerProvider
        ex = Executor(sandbox_type="docker")
        assert isinstance(ex._provider, DockerProvider)

    def test_executor_accepts_explicit_provider(self) -> None:
        from hivecore.runtime.executor import Executor
        custom = SubprocessSandbox(timeout=99)
        ex = Executor(provider=custom)
        assert ex._provider is custom

    def test_executor_legacy_sandbox_kwarg(self) -> None:
        """Passing sandbox= (old API) still works when it is an ExecutionProvider."""
        from hivecore.runtime.executor import Executor
        legacy = SubprocessSandbox()
        ex = Executor(sandbox=legacy)
        assert ex._provider is legacy
