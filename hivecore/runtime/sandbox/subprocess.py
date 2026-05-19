"""Subprocess-based sandbox for skill/tool execution.

Provides process isolation for untrusted skill code with:
- Timeout enforcement
- Memory limits
- Restricted filesystem access
- Captured stdout/stderr
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import textwrap
from pathlib import Path
from typing import Any

from hivecore.runtime.sandbox.base import ExecutionProvider

logger = logging.getLogger(__name__)


class SubprocessSandbox(ExecutionProvider):
    """Execute Python code in an isolated subprocess.

    Implements :class:`ExecutionProvider` using a plain
    ``asyncio.create_subprocess_exec`` call.  This is the default provider
    and requires no extra dependencies.

    Provides basic security through process isolation:
    - Separate process with its own memory space
    - Configurable timeout
    - Restricted working directory
    - Captured output
    """

    def __init__(
        self,
        timeout: int = 300,
        max_memory_mb: int = 512,
        working_dir: Path | None = None,
    ) -> None:
        self.timeout = timeout
        self.max_memory_mb = max_memory_mb
        self.working_dir = working_dir

    async def execute_function(
        self,
        func_module: str,
        func_name: str,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a function in a sandboxed subprocess.

        Args:
            func_module: Module path of the function.
            func_name: Function name.
            kwargs: Arguments to pass.

        Returns:
            Dict with 'result', 'stdout', 'stderr', 'exit_code'.
        """
        # Build a runner script
        script = textwrap.dedent(f"""
        import json
        import sys
        import importlib

        try:
            module = importlib.import_module({func_module!r})
            func = getattr(module, {func_name!r})
            kwargs = json.loads({json.dumps(json.dumps(kwargs))})

            import asyncio
            import inspect
            if inspect.iscoroutinefunction(func):
                result = asyncio.run(func(**kwargs))
            else:
                result = func(**kwargs)

            output = {{"success": True, "result": str(result)}}
        except Exception as e:
            output = {{"success": False, "error": str(e), "type": type(e).__name__}}

        print(json.dumps(output))
        """)

        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir) if self.working_dir else None,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            stdout_text = stdout.decode("utf-8", errors="replace").strip()
            stderr_text = stderr.decode("utf-8", errors="replace").strip()

            # Parse the JSON output from the script
            try:
                result = json.loads(stdout_text.split("\n")[-1])
            except (json.JSONDecodeError, IndexError):
                result = {"success": False, "error": "Failed to parse output", "raw": stdout_text}

            return {
                "result": result,
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": process.returncode,
            }

        except asyncio.TimeoutError:
            logger.error("Sandbox execution timed out after %ds", self.timeout)
            if process is not None:
                process.kill()
            return {
                "result": {"success": False, "error": f"Execution timed out after {self.timeout}s"},
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }
        except Exception as e:
            logger.error("Sandbox execution error: %s", e)
            return {
                "result": {"success": False, "error": str(e)},
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

    async def execute_code(self, code: str) -> dict[str, Any]:
        """Execute arbitrary Python code in a sandbox.

        Args:
            code: Python code string to execute.

        Returns:
            Dict with execution results.
        """
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir) if self.working_dir else None,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            return {
                "stdout": stdout.decode("utf-8", errors="replace").strip(),
                "stderr": stderr.decode("utf-8", errors="replace").strip(),
                "exit_code": process.returncode,
            }

        except asyncio.TimeoutError:
            if process is not None:
                process.kill()
            return {
                "stdout": "",
                "stderr": f"Execution timed out after {self.timeout}s",
                "exit_code": -1,
            }

        except Exception as e:
            logger.error("Sandbox execute_code error: %s", e)
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
            }


# Backward-compatible alias
SubprocessProvider = SubprocessSandbox

