"""Unit tests for Executor (runtime/executor.py).

Coverage targets:
- __init__: default registry, explicit provider, legacy sandbox arg
- execute(): unknown tool → error dict, known tool success, known tool exception
- execute() with use_sandbox=True and requires_confirmation=True → _execute_sandboxed
- execute() with use_sandbox=True and requires_confirmation=False → direct execute
- get_execution_log(): limit param
- get_stats(): total/successful/failed/avg_time
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hivecore.core.tools.base import FunctionTool
from hivecore.core.tools.registry import ToolRegistry
from hivecore.runtime.executor import Executor
from hivecore.runtime.sandbox.base import ExecutionProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(*tools) -> ToolRegistry:
    reg = ToolRegistry()
    for t in tools:
        reg.register(t)
    return reg


def _make_tool(name: str, result: str = "ok", raises: Exception | None = None, requires_confirmation: bool = False) -> FunctionTool:
    async def _fn(**kwargs: Any) -> str:
        if raises is not None:
            raise raises
        return result

    return FunctionTool(func=_fn, name=name, requires_confirmation=requires_confirmation)


class _FakeProvider(ExecutionProvider):
    """Minimal concrete ExecutionProvider implementation for testing."""

    async def execute_function(self, func_module: str, func_name: str, kwargs: dict) -> dict:
        return {"result": {"success": True, "result": "ok"}, "stdout": "", "stderr": "", "exit_code": 0}

    async def execute_code(self, code: str) -> dict:
        return {"stdout": "sandbox output", "stderr": "", "exit_code": 0}


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestExecutorInit:
    def test_default_creates_registry_and_provider(self) -> None:
        with patch("hivecore.runtime.executor.get_execution_provider") as mock_factory:
            mock_factory.return_value = _FakeProvider()
            ex = Executor()
        assert ex._tools is not None
        assert ex._execution_log == []
        mock_factory.assert_called_once_with("subprocess")

    def test_explicit_provider_used(self) -> None:
        provider = _FakeProvider()
        ex = Executor(provider=provider)
        assert ex._provider is provider

    def test_explicit_tool_registry_used(self) -> None:
        # Pre-register a tool so the registry is truthy (len > 0)
        # — an empty ToolRegistry is falsy due to __len__, so `or` would create a new one.
        reg = _make_registry(_make_tool("probe", result="x"))
        with patch("hivecore.runtime.executor.get_execution_provider", return_value=_FakeProvider()):
            ex = Executor(tool_registry=reg)
            assert ex._tools is reg

    def test_legacy_sandbox_arg(self) -> None:
        """Legacy callers may pass an ExecutionProvider as 'sandbox' kwarg."""
        provider = _FakeProvider()
        with patch("hivecore.runtime.executor.get_execution_provider", return_value=_FakeProvider()):
            ex = Executor(sandbox=provider)
        assert ex._provider is provider

    def test_sandbox_type_forwarded_to_factory(self) -> None:
        with patch("hivecore.runtime.executor.get_execution_provider") as mock_factory:
            mock_factory.return_value = _FakeProvider()
            Executor(sandbox_type="docker")
        mock_factory.assert_called_once_with("docker")


# ---------------------------------------------------------------------------
# execute() — unknown tool
# ---------------------------------------------------------------------------

class TestExecuteUnknownTool:
    async def test_returns_error_for_unknown_tool(self) -> None:
        ex = Executor(provider=_FakeProvider())
        result = await ex.execute("nonexistent_tool", {})
        assert result["output"] == ""
        assert "nonexistent_tool" in result["error"]
        assert result["execution_time"] == 0

    async def test_unknown_tool_not_logged(self) -> None:
        """Unknown tool short-circuits before any log entry is written."""
        ex = Executor(provider=_FakeProvider())
        await ex.execute("ghost_tool", {})
        # Log is empty because we returned before reaching the log append
        assert ex.get_execution_log() == []


# ---------------------------------------------------------------------------
# execute() — happy path
# ---------------------------------------------------------------------------

class TestExecuteSuccess:
    async def test_returns_output(self) -> None:
        tool = _make_tool("greet", result="hello!")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        result = await ex.execute("greet", {})
        assert result["output"] == "hello!"
        assert result["error"] is None
        assert result["execution_time"] >= 0

    async def test_logs_successful_execution(self) -> None:
        tool = _make_tool("calc", result="42")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        await ex.execute("calc", {})
        log = ex.get_execution_log()
        assert len(log) == 1
        assert log[0]["tool"] == "calc"
        assert log[0]["success"] is True

    async def test_non_string_result_stringified(self) -> None:
        async def _numeric(**_) -> int:
            return 123

        tool = FunctionTool(func=_numeric, name="numeric")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        result = await ex.execute("numeric", {})
        assert result["output"] == "123"


# ---------------------------------------------------------------------------
# execute() — tool raises exception
# ---------------------------------------------------------------------------

class TestExecuteFailure:
    async def test_exception_captured_as_error(self) -> None:
        tool = _make_tool("bad", raises=ValueError("oops"))
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        result = await ex.execute("bad", {})
        assert result["output"] == ""
        assert "oops" in result["error"]

    async def test_failed_execution_logged(self) -> None:
        tool = _make_tool("bad", raises=RuntimeError("boom"))
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        await ex.execute("bad", {})
        log = ex.get_execution_log()
        assert len(log) == 1
        assert log[0]["success"] is False
        assert "boom" in log[0]["error"]


# ---------------------------------------------------------------------------
# execute() — use_sandbox paths
# ---------------------------------------------------------------------------

class TestExecuteSandbox:
    async def test_sandbox_skipped_when_no_confirmation_required(self) -> None:
        """use_sandbox=True but requires_confirmation=False → direct execute."""
        tool = _make_tool("safe", result="safe result", requires_confirmation=False)
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        result = await ex.execute("safe", {}, use_sandbox=True)
        assert result["output"] == "safe result"

    async def test_sandbox_invoked_when_confirmation_required(self) -> None:
        """use_sandbox=True and requires_confirmation=True → _execute_sandboxed."""
        tool = _make_tool("dangerous", result="sandboxed result", requires_confirmation=True)
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        with patch.object(ex, "_execute_sandboxed", new_callable=AsyncMock, return_value="sandboxed result") as mock_sb:
            result = await ex.execute("dangerous", {"x": 1}, use_sandbox=True)

        mock_sb.assert_called_once()
        assert result["output"] == "sandboxed result"


# ---------------------------------------------------------------------------
# get_execution_log()
# ---------------------------------------------------------------------------

class TestGetExecutionLog:
    async def test_default_limit(self) -> None:
        tool = _make_tool("t", result="x")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        for _ in range(60):
            await ex.execute("t", {})
        log = ex.get_execution_log()
        assert len(log) == 50  # default limit

    async def test_custom_limit(self) -> None:
        tool = _make_tool("t", result="x")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        for _ in range(10):
            await ex.execute("t", {})
        log = ex.get_execution_log(limit=5)
        assert len(log) == 5

    async def test_log_is_most_recent(self) -> None:
        """get_execution_log(limit=n) returns the n most recent entries."""
        tools = [_make_tool(f"t{i}", result=str(i)) for i in range(5)]
        reg = _make_registry(*tools)
        ex = Executor(tool_registry=reg, provider=_FakeProvider())
        for i in range(5):
            await ex.execute(f"t{i}", {})
        log = ex.get_execution_log(limit=2)
        assert log[-1]["tool"] == "t4"


# ---------------------------------------------------------------------------
# get_stats()
# ---------------------------------------------------------------------------

class TestGetStats:
    async def test_empty_log(self) -> None:
        ex = Executor(provider=_FakeProvider())
        stats = ex.get_stats()
        assert stats["total_executions"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["avg_execution_time"] == 0

    async def test_all_successes(self) -> None:
        tool = _make_tool("ok", result="yes")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        for _ in range(3):
            await ex.execute("ok", {})
        stats = ex.get_stats()
        assert stats["total_executions"] == 3
        assert stats["successful"] == 3
        assert stats["failed"] == 0
        assert stats["avg_execution_time"] >= 0

    async def test_mixed_success_failure(self) -> None:
        ok_tool = _make_tool("ok", result="yes")
        bad_tool = _make_tool("bad", raises=RuntimeError("err"))
        reg = _make_registry(ok_tool, bad_tool)
        ex = Executor(tool_registry=reg, provider=_FakeProvider())
        await ex.execute("ok", {})
        await ex.execute("bad", {})
        await ex.execute("ok", {})
        stats = ex.get_stats()
        assert stats["total_executions"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1

    async def test_avg_time_rounded(self) -> None:
        tool = _make_tool("t", result="v")
        ex = Executor(tool_registry=_make_registry(tool), provider=_FakeProvider())
        await ex.execute("t", {})
        stats = ex.get_stats()
        # avg_execution_time should be rounded to 3 decimal places
        assert stats["avg_execution_time"] == round(stats["avg_execution_time"], 3)
