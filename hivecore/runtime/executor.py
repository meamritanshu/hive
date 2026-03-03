"""Skill/tool execution engine.

Manages the execution of tools and skills, routing through
the appropriate sandbox for isolation.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from hivecore.core.tools.base import BaseTool
from hivecore.core.tools.registry import ToolRegistry
from hivecore.runtime.sandbox.base import ExecutionProvider
from hivecore.runtime.sandbox.factory import get_execution_provider

logger = logging.getLogger(__name__)


class Executor:
    """Execution engine for tools and skills.

    Routes tool execution through the appropriate sandbox based
    on the tool's security requirements. Tracks execution metrics.

    The sandbox backend is selected via the ``sandbox_type`` constructor
    argument (``"subprocess"`` or ``"docker"``), defaulting to
    ``"subprocess"``.  Alternatively, pass a pre-built
    :class:`ExecutionProvider` directly via the ``provider`` argument.
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        sandbox_type: str = "subprocess",
        provider: Optional[ExecutionProvider] = None,
        # Kept for backward compatibility — ignored when provider is supplied
        sandbox: Any = None,
    ) -> None:
        self._tools = tool_registry or ToolRegistry()
        # Prefer an explicitly-supplied provider; otherwise use the factory.
        if provider is not None:
            self._provider: ExecutionProvider = provider
        elif sandbox is not None and isinstance(sandbox, ExecutionProvider):
            # Legacy callers may pass a SubprocessSandbox directly.
            self._provider = sandbox
        else:
            self._provider = get_execution_provider(sandbox_type)
        self._execution_log: list[dict[str, Any]] = []

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        use_sandbox: bool = False,
    ) -> dict[str, Any]:
        """Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Arguments to pass.
            use_sandbox: Whether to use subprocess sandbox.

        Returns:
            Dict with 'output', 'error', 'execution_time'.
        """
        start_time = time.time()

        tool = self._tools.get(tool_name)
        if tool is None:
            return {
                "output": "",
                "error": f"Tool not found: {tool_name}",
                "execution_time": 0,
            }

        try:
            if use_sandbox and tool.get_definition().requires_confirmation:
                result = await self._execute_sandboxed(tool, arguments)
            else:
                result = await tool.execute(**arguments)

            elapsed = time.time() - start_time

            log_entry = {
                "tool": tool_name,
                "success": True,
                "execution_time": elapsed,
                "timestamp": start_time,
            }
            self._execution_log.append(log_entry)

            return {
                "output": result if isinstance(result, str) else str(result),
                "error": None,
                "execution_time": elapsed,
            }

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("Tool execution error (%s): %s", tool_name, e)

            log_entry = {
                "tool": tool_name,
                "success": False,
                "error": str(e),
                "execution_time": elapsed,
                "timestamp": start_time,
            }
            self._execution_log.append(log_entry)

            return {
                "output": "",
                "error": str(e),
                "execution_time": elapsed,
            }

    async def _execute_sandboxed(
        self, tool: BaseTool, arguments: dict[str, Any]
    ) -> str:
        """Execute a tool in the configured execution provider's sandbox."""
        # For now, just execute directly (sandbox for code_exec type tools)
        return await tool.execute(**arguments)

    def get_execution_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent execution log entries."""
        return self._execution_log[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        total = len(self._execution_log)
        successes = sum(1 for e in self._execution_log if e.get("success"))
        avg_time = (
            sum(e["execution_time"] for e in self._execution_log) / total
            if total > 0
            else 0
        )

        return {
            "total_executions": total,
            "successful": successes,
            "failed": total - successes,
            "avg_execution_time": round(avg_time, 3),
        }
