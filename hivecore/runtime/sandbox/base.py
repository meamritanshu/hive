"""Abstract base for execution providers.

All sandbox backends (subprocess, Docker, …) implement this interface so
the rest of the framework can swap providers without changing call sites.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ExecutionProvider(ABC):
    """Abstract interface for sandboxed skill/code execution.

    Implementations must be safe to call from an async context.
    """

    @abstractmethod
    async def execute_function(
        self,
        func_module: str,
        func_name: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a named Python function in the provider's sandbox.

        Args:
            func_module: Dotted import path of the module (e.g. ``"myskill.main"``).
            func_name: Name of the callable inside that module.
            kwargs: Keyword arguments to pass to the function.

        Returns:
            Dict with keys:

            - ``result``: sub-dict with ``success`` bool and either ``result``
              (str) or ``error`` (str).
            - ``stdout``: captured stdout text.
            - ``stderr``: captured stderr text.
            - ``exit_code``: process exit code (int).
        """

    @abstractmethod
    async def execute_code(self, code: str) -> dict[str, Any]:
        """Execute an arbitrary Python code string in the provider's sandbox.

        Args:
            code: Python source code to run.

        Returns:
            Dict with keys ``stdout``, ``stderr``, ``exit_code``.
        """
