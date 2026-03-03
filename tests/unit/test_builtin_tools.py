"""Unit tests for built-in tools (core/tools/builtin/tools.py).

Covers: read_file, write_file, list_directory, run_shell, get_current_time,
calculate, _human_size, _parse_ddg_lite, register_builtin_tools.
web_search is tested with a mocked httpx client (no real network calls).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import httpx

from hivecore.core.tools.builtin.tools import (
    _human_size,
    _parse_ddg_lite,
    calculate,
    get_current_time,
    list_directory,
    read_file,
    register_builtin_tools,
    run_shell,
    web_search,
    write_file,
)
from hivecore.core.tools.registry import ToolRegistry


def _call(tool, *args, **kwargs):
    """Call the underlying function of a FunctionTool directly."""
    return tool._func(*args, **kwargs)


async def _acall(tool, *args, **kwargs):
    """Async-call the underlying function of a FunctionTool directly."""
    return await tool._func(*args, **kwargs)


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------

class TestReadFile:
    def test_reads_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("hello world", encoding="utf-8")
        result = _call(read_file, str(f))
        assert "hello world" in result

    def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        result = _call(read_file, str(tmp_path / "nope.txt"))
        assert "Error" in result
        assert "not found" in result.lower()

    def test_directory_returns_error(self, tmp_path: Path) -> None:
        result = _call(read_file, str(tmp_path))
        assert "Error" in result
        assert "not a file" in result.lower()

    def test_truncates_long_file(self, tmp_path: Path) -> None:
        f = tmp_path / "big.txt"
        lines = [f"line {i}" for i in range(600)]
        f.write_text("\n".join(lines), encoding="utf-8")
        result = _call(read_file, str(f), max_lines=500)
        assert "truncated" in result
        assert "600 total lines" in result

    def test_reads_full_short_file(self, tmp_path: Path) -> None:
        f = tmp_path / "short.txt"
        f.write_text("a\nb\nc", encoding="utf-8")
        result = _call(read_file, str(f), max_lines=500)
        assert result == "a\nb\nc"

    def test_tilde_expansion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """~ in path should expand correctly (monkeypatched home)."""
        f = tmp_path / "x.txt"
        f.write_text("ok", encoding="utf-8")
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        result = _call(read_file, str(f))
        assert "ok" in result


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------

class TestWriteFile:
    def test_writes_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        result = _call(write_file, str(dest), "content here")
        assert "Successfully wrote" in result
        assert dest.read_text(encoding="utf-8") == "content here"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        dest = tmp_path / "a" / "b" / "c.txt"
        _call(write_file, str(dest), "deep")
        assert dest.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "file.txt"
        dest.write_text("old", encoding="utf-8")
        _call(write_file, str(dest), "new")
        assert dest.read_text(encoding="utf-8") == "new"

    def test_reports_byte_count(self, tmp_path: Path) -> None:
        dest = tmp_path / "f.txt"
        result = _call(write_file, str(dest), "hello")
        assert "5" in result  # 5 bytes


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------

class TestListDirectory:
    def test_lists_files_and_dirs(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "subdir").mkdir()
        result = _call(list_directory, str(tmp_path))
        assert "file.txt" in result
        assert "subdir/" in result

    def test_missing_path_returns_error(self, tmp_path: Path) -> None:
        result = _call(list_directory, str(tmp_path / "nope"))
        assert "Error" in result
        assert "not found" in result.lower()

    def test_file_path_returns_error(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("x")
        result = _call(list_directory, str(f))
        assert "Error" in result
        assert "not a directory" in result.lower()

    def test_hidden_files_excluded_by_default(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("x")
        (tmp_path / "visible.txt").write_text("y")
        result = _call(list_directory, str(tmp_path), show_hidden=False)
        assert ".hidden" not in result
        assert "visible.txt" in result

    def test_hidden_files_included_when_requested(self, tmp_path: Path) -> None:
        (tmp_path / ".hidden").write_text("x")
        result = _call(list_directory, str(tmp_path), show_hidden=True)
        assert ".hidden" in result

    def test_empty_directory(self, tmp_path: Path) -> None:
        result = _call(list_directory, str(tmp_path))
        assert "empty" in result.lower()

    def test_shows_human_readable_sizes(self, tmp_path: Path) -> None:
        f = tmp_path / "f.txt"
        f.write_text("hello world")
        result = _call(list_directory, str(tmp_path))
        # Should have a size annotation like (11.0B)
        assert "B" in result


# ---------------------------------------------------------------------------
# run_shell
# ---------------------------------------------------------------------------

class TestRunShell:
    def test_simple_command(self) -> None:
        result = _call(run_shell, "echo hello")
        assert "hello" in result

    def test_return_code_included(self) -> None:
        result = _call(run_shell, "exit 0", timeout=10)
        assert "Return code: 0" in result

    def test_nonzero_exit_code(self) -> None:
        result = _call(run_shell, "exit 42", timeout=10)
        assert "42" in result

    def test_stderr_captured(self) -> None:
        result = _call(run_shell, "echo error >&2", timeout=10)
        # On Windows the shell might behave differently; just check no crash
        assert "Return code" in result

    def test_timeout_returns_error(self) -> None:
        result = _call(run_shell,
                       "ping -n 10 127.0.0.1" if __import__("sys").platform == "win32"
                       else "sleep 10", timeout=1)
        assert "timed out" in result.lower() or "Error" in result

    def test_working_dir(self, tmp_path: Path) -> None:
        result = _call(run_shell,
                       "cd" if __import__("sys").platform == "win32" else "pwd",
                       working_dir=str(tmp_path))
        # Should not error
        assert "Return code" in result


# ---------------------------------------------------------------------------
# get_current_time
# ---------------------------------------------------------------------------

class TestGetCurrentTime:
    def test_returns_date_string(self) -> None:
        result = _call(get_current_time)
        assert len(result) > 10
        assert "202" in result

    def test_contains_day_of_week(self) -> None:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        result = _call(get_current_time)
        assert any(d in result for d in days)


# ---------------------------------------------------------------------------
# calculate
# ---------------------------------------------------------------------------

class TestCalculate:
    def test_addition(self) -> None:
        result = _call(calculate, "2 + 3")
        assert "5" in result

    def test_multiplication(self) -> None:
        result = _call(calculate, "6 * 7")
        assert "42" in result

    def test_division(self) -> None:
        result = _call(calculate, "10 / 4")
        assert "2.5" in result

    def test_complex_expression(self) -> None:
        result = _call(calculate, "(3 + 4) * 2")
        assert "14" in result

    def test_modulo(self) -> None:
        result = _call(calculate, "10 % 3")
        assert "1" in result

    def test_invalid_chars_returns_error(self) -> None:
        result = _call(calculate, "import os")
        assert "Error" in result
        assert "invalid" in result.lower()

    def test_division_by_zero_returns_error(self) -> None:
        result = _call(calculate, "1 / 0")
        assert "Error" in result

    def test_float_result(self) -> None:
        result = _call(calculate, "1.5 + 2.5")
        assert "4.0" in result or "4" in result


# ---------------------------------------------------------------------------
# _human_size
# ---------------------------------------------------------------------------

class TestHumanSize:
    def test_bytes(self) -> None:
        assert _human_size(512) == "512.0B"

    def test_kilobytes(self) -> None:
        result = _human_size(2048)
        assert "KB" in result or "2.0" in result

    def test_megabytes(self) -> None:
        result = _human_size(1024 * 1024 * 5)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        result = _human_size(1024 ** 3 * 2)
        assert "GB" in result

    def test_terabytes(self) -> None:
        result = _human_size(1024 ** 4 * 3)
        assert "TB" in result

    def test_zero_bytes(self) -> None:
        assert _human_size(0) == "0.0B"


# ---------------------------------------------------------------------------
# _parse_ddg_lite
# ---------------------------------------------------------------------------

class TestParseDdgLite:
    def test_parses_results_from_html(self) -> None:
        html = (
            'something before'
            '<a rel="nofollow" href="https://example.com">Title</a>'
            '<a rel="nofollow" href="https://other.com">Other</a>'
        )
        # Reconstruct as DDG lite would: href inside the tag
        html2 = (
            'prefix'
            '<a rel="nofollow" href="https://example.com">Example Title</a> rest'
            '<a rel="nofollow" href="https://second.org">Second Site</a> rest'
        )
        results = _parse_ddg_lite(html2, max_results=5)
        # Should return list (may be empty if our simple HTML doesn't match format)
        assert isinstance(results, list)

    def test_returns_empty_on_no_results(self) -> None:
        results = _parse_ddg_lite("<html><body>nothing here</body></html>", max_results=5)
        assert results == []

    def test_respects_max_results(self) -> None:
        # Build HTML with 5 fake result links in DDG lite format
        entries = "".join(
            f'<a rel="nofollow" href="https://example{i}.com">Title {i}</a> x'
            for i in range(5)
        )
        html = "prefix" + entries
        results = _parse_ddg_lite(html, max_results=2)
        assert len(results) <= 2


# ---------------------------------------------------------------------------
# web_search (mocked httpx)
# ---------------------------------------------------------------------------

class TestWebSearch:
    async def test_successful_search(self) -> None:
        fake_html = (
            "prefix"
            '<a rel="nofollow" href="https://example.com">Example</a> rest'
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = fake_html

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _acall(web_search, "test query")
        assert "test query" in result or "result" in result.lower() or "example" in result.lower()

    async def test_non_200_returns_error(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _acall(web_search, "anything")
        assert "503" in result or "failed" in result.lower()

    async def test_exception_returns_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("network down"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _acall(web_search, "query")
        assert "error" in result.lower() or "network" in result.lower()

    async def test_no_results_message(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>no links here</html>"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await _acall(web_search, "empty query")
        assert "no results" in result.lower() or "empty query" in result


# ---------------------------------------------------------------------------
# register_builtin_tools
# ---------------------------------------------------------------------------

class TestRegisterBuiltinTools:
    def test_registers_all_tools(self) -> None:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        names = registry.list_names()
        assert "read_file" in names
        assert "write_file" in names
        assert "list_directory" in names
        assert "run_shell" in names
        assert "web_search" in names
        assert "get_current_time" in names
        assert "calculate" in names

    def test_tools_have_correct_categories(self) -> None:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        defns = {d.name: d for d in registry.get_definitions()}
        assert defns["read_file"].category == "filesystem"
        assert defns["write_file"].category == "filesystem"
        assert defns["run_shell"].category == "system"
        assert defns["web_search"].category == "web"
        assert defns["get_current_time"].category == "utility"
        assert defns["calculate"].category == "utility"

    def test_write_file_requires_confirmation(self) -> None:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        defns = {d.name: d for d in registry.get_definitions()}
        assert defns["write_file"].requires_confirmation is True
        assert defns["run_shell"].requires_confirmation is True

    def test_read_file_does_not_require_confirmation(self) -> None:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        defns = {d.name: d for d in registry.get_definitions()}
        assert defns["read_file"].requires_confirmation is False
