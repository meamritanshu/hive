"""Built-in tools for common operations.

These are the default tools available to the agent out of the box.
"""

from __future__ import annotations

import datetime
import subprocess
from pathlib import Path

from hivecore.core.tools.base import tool


@tool(name="read_file", description="Read the contents of a file.", category="filesystem")
def read_file(path: str, max_lines: int = 500) -> str:
    """Read a file and return its contents.

    Args:
        path: Path to the file to read.
        max_lines: Maximum number of lines to return.
    """
    file_path = Path(path).expanduser().resolve()
    if not file_path.exists():
        return f"Error: File not found: {file_path}"
    if not file_path.is_file():
        return f"Error: Not a file: {file_path}"

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n... (truncated, {len(lines)} total lines)"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


@tool(name="write_file", description="Write content to a file.", category="filesystem",
      requires_confirmation=True)
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating directories as needed.

    Args:
        path: Path to the file to write.
        content: Content to write.
    """
    file_path = Path(path).expanduser().resolve()
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} bytes to {file_path}"
    except Exception as e:
        return f"Error writing file: {e}"


@tool(name="list_directory", description="List files and directories in a path.",
      category="filesystem")
def list_directory(path: str = ".", show_hidden: bool = False) -> str:
    """List contents of a directory.

    Args:
        path: Directory path to list.
        show_hidden: Whether to include hidden files.
    """
    dir_path = Path(path).expanduser().resolve()
    if not dir_path.exists():
        return f"Error: Path not found: {dir_path}"
    if not dir_path.is_dir():
        return f"Error: Not a directory: {dir_path}"

    entries = []
    try:
        for entry in sorted(dir_path.iterdir()):
            if not show_hidden and entry.name.startswith("."):
                continue
            suffix = "/" if entry.is_dir() else ""
            size = entry.stat().st_size if entry.is_file() else 0
            entries.append(f"  {entry.name}{suffix}  ({_human_size(size)})" if size else
                           f"  {entry.name}{suffix}")
        return f"Contents of {dir_path}:\n" + "\n".join(entries) if entries else "Directory is empty."
    except PermissionError:
        return f"Error: Permission denied: {dir_path}"


@tool(name="run_shell", description="Execute a shell command and return its output.",
      category="system", requires_confirmation=True)
def run_shell(command: str, timeout: int = 60, working_dir: str | None = None) -> str:
    """Execute a shell command.

    Args:
        command: Shell command to execute.
        timeout: Timeout in seconds.
        working_dir: Working directory for the command.
    """
    cwd = Path(working_dir).expanduser().resolve() if working_dir else None
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        output = ""
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        output += f"Return code: {result.returncode}"
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {e}"


@tool(name="web_search", description="Search the web for information using a query.",
      category="web")
async def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using httpx.

    Args:
        query: Search query.
        num_results: Number of results to return.
    """
    import httpx

    try:
        # Use DuckDuckGo Lite as a free search endpoint
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={"User-Agent": "HiveCore/0.1"},
            )

            if response.status_code != 200:
                return f"Search failed with status {response.status_code}"

            # Parse basic results from the HTML
            text = response.text
            results = _parse_ddg_lite(text, num_results)
            if results:
                return f"Search results for '{query}':\n\n" + "\n\n".join(results)
            return f"No results found for '{query}'"
    except Exception as e:
        return f"Search error: {e}"


@tool(name="get_current_time", description="Get the current date and time.", category="utility")
def get_current_time() -> str:
    """Get the current date and time."""
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S (%A)")


@tool(name="calculate", description="Evaluate a mathematical expression.", category="utility")
def calculate(expression: str) -> str:
    """Safely evaluate a mathematical expression.

    Args:
        expression: Mathematical expression to evaluate.
    """
    # Only allow safe math operations
    allowed_chars = set("0123456789+-*/.()% ")
    if not all(c in allowed_chars for c in expression):
        return "Error: Expression contains invalid characters. Only numbers and +-*/.()% are allowed."

    try:
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error evaluating expression: {e}"


def _human_size(size: int) -> str:
    """Convert bytes to human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f}{unit}"
        size //= 1024
    return f"{size:.1f}TB"


def _parse_ddg_lite(html: str, max_results: int) -> list[str]:
    """Parse DuckDuckGo Lite HTML for search results."""
    results = []
    # Simple regex-free parsing for DDG Lite results
    parts = html.split('<a rel="nofollow"')
    for part in parts[1:max_results + 1]:
        try:
            href_start = part.index('href="') + 6
            href_end = part.index('"', href_start)
            url = part[href_start:href_end]

            # Extract text
            text_start = part.index(">") + 1
            text_end = part.index("</a>")
            title = part[text_start:text_end].strip()

            # Clean HTML tags from title
            import re
            title = re.sub(r"<[^>]+>", "", title)

            results.append(f"- [{title}]({url})")
        except (ValueError, IndexError):
            continue
    return results


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools with a ToolRegistry.

    Args:
        registry: The registry to add tools to.
    """

    builtin_tools = [
        read_file,
        write_file,
        list_directory,
        run_shell,
        web_search,
        get_current_time,
        calculate,
    ]
    for t in builtin_tools:
        registry.register(t)
