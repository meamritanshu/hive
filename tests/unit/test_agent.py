"""Unit tests for the Agent's ReAct loop — Fix 3a: self-reflection/critic step.

Also covers:
- run_stream()
- _retrieve_memory() — with / without memory manager, exception path
- _store_memory() — with / without memory manager, exception path
- _update_system_prompt()
- register_tool()
- clear_conversation()
- memory_stats()
- shutdown()
- initialize() — LLM auto-created via registry when not supplied
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from hivecore.core.agent import Agent
from hivecore.core.messages import Message, ToolCall, ToolResult
from hivecore.core.tools.base import FunctionTool
from hivecore.core.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tool_call(name: str = "dummy", **kwargs: Any) -> ToolCall:
    return ToolCall(name=name, arguments=kwargs)


def _assistant_with_calls(*tool_calls: ToolCall) -> Message:
    """Return an assistant message that contains tool calls."""
    msg = Message.assistant("")
    msg.tool_calls = list(tool_calls)
    return msg


def _assistant_final(content: str = "Final answer") -> Message:
    """Return an assistant message with no tool calls (final answer)."""
    return Message.assistant(content)


def _make_llm_sequence(*messages: Message) -> AsyncMock:
    """Return an LLM mock whose ``complete()`` returns messages in sequence."""
    mock = AsyncMock()
    mock.complete = AsyncMock(side_effect=list(messages))
    return mock


# ---------------------------------------------------------------------------
# Tests: normal (no-failure) path
# ---------------------------------------------------------------------------

class TestReActLoopNormal:
    """Basic ReAct loop behaviour — no failures."""

    async def test_single_step_final_answer(self) -> None:
        """LLM returns a final answer on the first call — no tools needed."""
        llm = _make_llm_sequence(_assistant_final("Hello!"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        result = await agent.run("Hi")
        assert result.content == "Hello!"
        assert llm.complete.call_count == 1

    async def test_tool_call_then_final_answer(self) -> None:
        """LLM calls one tool, gets result, then gives final answer."""
        tc = _make_tool_call("dummy_tool", x=1)
        llm = _make_llm_sequence(
            _assistant_with_calls(tc),
            _assistant_final("Done"),
        )

        async def dummy_tool(x: int) -> str:
            return "ok"

        registry = ToolRegistry()
        registry.register(FunctionTool(func=dummy_tool, name="dummy_tool"))

        agent = Agent(llm_provider=llm, tool_registry=registry)
        await agent.initialize()
        result = await agent.run("Do something")
        assert result.content == "Done"
        assert llm.complete.call_count == 2


# ---------------------------------------------------------------------------
# Tests: self-reflection trigger
# ---------------------------------------------------------------------------

class TestSelfReflectionCritic:
    """Verify the self-reflection step fires after 3 consecutive tool failures."""

    async def test_reflection_injected_after_threshold(self) -> None:
        """After _REFLECTION_FAILURE_THRESHOLD consecutive failures, a
        self-reflection user message is added and the counter resets."""

        threshold = Agent._REFLECTION_FAILURE_THRESHOLD  # 3

        # Build a tool that always raises
        async def bad_tool(**_: Any) -> str:
            raise RuntimeError("boom")

        registry = ToolRegistry()
        registry.register(FunctionTool(func=bad_tool, name="bad_tool"))

        tc = _make_tool_call("bad_tool")

        # LLM repeatedly requests the failing tool, then finally gives an answer
        llm_responses = (
            [_assistant_with_calls(tc)] * threshold  # threshold calls with tool
            + [_assistant_final("Gave up")]
        )
        llm = _make_llm_sequence(*llm_responses)

        agent = Agent(llm_provider=llm, tool_registry=registry)
        await agent.initialize()
        result = await agent.run("break things")

        # The final answer should come through
        assert result.content == "Gave up"

        # A self-reflection message should have been injected into the conversation
        self_reflection_msgs = [
            m for m in agent._conversation.messages
            if m.role.value == "user" and "Self-Reflection" in m.content
        ]
        assert len(self_reflection_msgs) >= 1, (
            "Expected at least one self-reflection message in conversation"
        )

    async def test_reflection_counter_resets_on_success(self) -> None:
        """A successful tool call resets the consecutive failure counter,
        so reflection is NOT triggered even if there were prior failures."""

        threshold = Agent._REFLECTION_FAILURE_THRESHOLD  # 3

        call_count = {"n": 0}

        async def flaky_tool(**_: Any) -> str:
            call_count["n"] += 1
            # First (threshold-1) calls fail, then succeed
            if call_count["n"] < threshold:
                raise RuntimeError("not yet")
            return "success"

        registry = ToolRegistry()
        registry.register(FunctionTool(func=flaky_tool, name="flaky_tool"))

        tc = _make_tool_call("flaky_tool")
        # threshold calls with tool, then final
        llm_responses = [_assistant_with_calls(tc)] * threshold + [_assistant_final("OK")]
        llm = _make_llm_sequence(*llm_responses)

        agent = Agent(llm_provider=llm, tool_registry=registry)
        await agent.initialize()
        await agent.run("use flaky")

        # No self-reflection should have been injected (success reset the counter)
        self_reflection_msgs = [
            m for m in agent._conversation.messages
            if m.role.value == "user" and "Self-Reflection" in m.content
        ]
        assert len(self_reflection_msgs) == 0

    async def test_reflection_content_is_diagnostic(self) -> None:
        """The injected self-reflection message contains useful diagnostic keywords."""

        threshold = Agent._REFLECTION_FAILURE_THRESHOLD

        async def always_fail(**_: Any) -> str:
            raise RuntimeError("nope")

        registry = ToolRegistry()
        registry.register(FunctionTool(func=always_fail, name="always_fail"))

        tc = _make_tool_call("always_fail")
        llm_responses = [_assistant_with_calls(tc)] * threshold + [_assistant_final("done")]
        llm = _make_llm_sequence(*llm_responses)

        agent = Agent(llm_provider=llm, tool_registry=registry)
        await agent.initialize()
        await agent.run("fail")

        reflection_msgs = [
            m for m in agent._conversation.messages
            if m.role.value == "user" and "Self-Reflection" in m.content
        ]
        assert reflection_msgs, "No self-reflection message found"
        content = reflection_msgs[0].content
        assert "consecutive" in content.lower() or "failing" in content.lower()
        assert "tool" in content.lower()

    async def test_max_iterations_still_respected(self) -> None:
        """Even with reflection logic, max_iterations cap still terminates the loop."""
        from hivecore.config.settings import HiveSettings

        settings = HiveSettings()
        settings.agent.max_iterations = 3

        async def bad(**_: Any) -> str:
            raise RuntimeError("fail")

        registry = ToolRegistry()
        registry.register(FunctionTool(func=bad, name="bad"))

        tc = _make_tool_call("bad")
        # Provide exactly max_iterations tool-call responses, then the fallback
        # that the post-loop summary call will consume.
        final = _assistant_final("fallback")
        llm = _make_llm_sequence(
            _assistant_with_calls(tc),  # iteration 0
            _assistant_with_calls(tc),  # iteration 1
            _assistant_with_calls(tc),  # iteration 2  → max reached
            final,                      # summary call after the loop
        )

        agent = Agent(settings=settings, llm_provider=llm, tool_registry=registry)
        await agent.initialize()
        result = await agent.run("stress")

        # Should terminate after max_iterations with the summary/fallback message
        assert result.content == "fallback"
        assert llm.complete.call_count == 4  # 3 loop iterations + 1 summary

    async def test_unknown_tool_counts_as_failure(self) -> None:
        """Calling a non-existent tool produces a ToolResult.error, which
        increments the consecutive failure counter."""

        threshold = Agent._REFLECTION_FAILURE_THRESHOLD

        tc = _make_tool_call("no_such_tool")
        llm_responses = [_assistant_with_calls(tc)] * threshold + [_assistant_final("done")]
        llm = _make_llm_sequence(*llm_responses)

        agent = Agent(llm_provider=llm)  # empty tool registry
        await agent.initialize()
        await agent.run("use nonexistent tool")

        reflection_msgs = [
            m for m in agent._conversation.messages
            if m.role.value == "user" and "Self-Reflection" in m.content
        ]
        assert len(reflection_msgs) >= 1


# ---------------------------------------------------------------------------
# Tests: run_stream()
# ---------------------------------------------------------------------------

class TestRunStream:
    async def test_yields_chunks_and_complete_content(self) -> None:
        llm = _make_llm_sequence(_assistant_final("Hello streaming world!"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        chunks = []
        async for chunk in agent.run_stream("Hi"):
            chunks.append(chunk)

        full = "".join(chunks)
        assert full == "Hello streaming world!"
        assert len(chunks) > 0

    async def test_stream_stores_memory(self) -> None:
        """run_stream must call _store_memory after streaming."""
        llm = _make_llm_sequence(_assistant_final("response"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        with patch.object(agent, "_store_memory", new_callable=AsyncMock) as mock_store:
            async for _ in agent.run_stream("input"):
                pass

        mock_store.assert_called_once_with("input", "response")

    async def test_stream_with_tool_call(self) -> None:
        """run_stream executes tool calls silently before streaming the final answer."""
        tc = _make_tool_call("tool_x")

        async def tool_x(**_: Any) -> str:
            return "tool output"

        registry = ToolRegistry()
        registry.register(FunctionTool(func=tool_x, name="tool_x"))

        llm = _make_llm_sequence(
            _assistant_with_calls(tc),
            _assistant_final("Final after tool"),
        )
        agent = Agent(llm_provider=llm, tool_registry=registry)
        await agent.initialize()

        chunks = []
        async for chunk in agent.run_stream("run tool"):
            chunks.append(chunk)

        assert "".join(chunks) == "Final after tool"


# ---------------------------------------------------------------------------
# Tests: _retrieve_memory() / _store_memory()
# ---------------------------------------------------------------------------

class TestMemoryHooks:
    async def test_retrieve_returns_empty_when_no_manager(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        agent._memory_manager = None

        result = await agent._retrieve_memory("query")
        assert result == ""

    async def test_retrieve_returns_formatted_context(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.retrieve = AsyncMock(return_value=[
            {"type": "episodic", "content": "I like Python"},
            {"type": "personal", "content": "Name is Alice"},
        ])
        agent._memory_manager = mock_mgr

        result = await agent._retrieve_memory("what do I like?")
        assert "Python" in result
        assert "Alice" in result

    async def test_retrieve_returns_empty_on_empty_memories(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.retrieve = AsyncMock(return_value=[])
        agent._memory_manager = mock_mgr

        result = await agent._retrieve_memory("query")
        assert result == ""

    async def test_retrieve_swallows_exception(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.retrieve = AsyncMock(side_effect=RuntimeError("db error"))
        agent._memory_manager = mock_mgr

        result = await agent._retrieve_memory("query")
        assert result == ""

    async def test_store_noop_when_no_manager(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        agent._memory_manager = None

        # Must not raise
        await agent._store_memory("user msg", "agent response")

    async def test_store_calls_store_conversation(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.store_conversation = AsyncMock()
        agent._memory_manager = mock_mgr

        await agent._store_memory("hello", "world")
        mock_mgr.store_conversation.assert_called_once_with(
            user_message="hello",
            assistant_message="world",
        )

    async def test_store_swallows_exception(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.store_conversation = AsyncMock(side_effect=RuntimeError("write fail"))
        agent._memory_manager = mock_mgr

        # Must not raise
        await agent._store_memory("hello", "world")


# ---------------------------------------------------------------------------
# Tests: _update_system_prompt()
# ---------------------------------------------------------------------------

class TestUpdateSystemPrompt:
    async def test_replaces_system_message(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        original_sys = agent._conversation.messages[0].content
        agent._update_system_prompt("Memory: I love Rust")
        updated_sys = agent._conversation.messages[0].content

        assert updated_sys != original_sys
        assert "Rust" in updated_sys

    async def test_noop_on_empty_conversation(self) -> None:
        """Should not crash when messages list is empty."""
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        agent._conversation.messages.clear()

        # Must not raise
        agent._update_system_prompt("some context")


# ---------------------------------------------------------------------------
# Tests: register_tool()
# ---------------------------------------------------------------------------

class TestRegisterTool:
    async def test_tool_available_after_register(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        async def my_tool(**_: Any) -> str:
            return "custom"

        tool = FunctionTool(func=my_tool, name="my_tool")
        agent.register_tool(tool)

        assert agent._tools.get("my_tool") is tool


# ---------------------------------------------------------------------------
# Tests: clear_conversation()
# ---------------------------------------------------------------------------

class TestClearConversation:
    async def test_clears_history(self) -> None:
        """clear_conversation() removes non-system messages, keeping the system prompt."""
        llm = _make_llm_sequence(_assistant_final("ok"), _assistant_final("ok2"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        await agent.run("first message")
        pre_clear = len(agent._conversation.messages)
        assert pre_clear > 1  # system + user + assistant

        await agent.clear_conversation()
        # System message is preserved; all others removed
        from hivecore.core.messages import Role
        remaining = agent._conversation.messages
        assert all(m.role == Role.SYSTEM for m in remaining)


# ---------------------------------------------------------------------------
# Tests: memory_stats()
# ---------------------------------------------------------------------------

class TestMemoryStats:
    async def test_returns_not_initialized_when_no_manager(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        agent._memory_manager = None

        result = await agent.memory_stats()
        assert "not initialized" in result.lower()

    async def test_returns_json_stats(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.get_stats = AsyncMock(return_value={"total": 5, "size": 100})
        agent._memory_manager = mock_mgr

        result = await agent.memory_stats()
        import json
        parsed = json.loads(result)
        assert parsed["total"] == 5

    async def test_returns_error_string_on_exception(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.get_stats = AsyncMock(side_effect=RuntimeError("stats error"))
        agent._memory_manager = mock_mgr

        result = await agent.memory_stats()
        assert "Error" in result


# ---------------------------------------------------------------------------
# Tests: shutdown()
# ---------------------------------------------------------------------------

class TestShutdown:
    async def test_shutdown_closes_memory_manager(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.close = AsyncMock()
        agent._memory_manager = mock_mgr

        await agent.shutdown()
        mock_mgr.close.assert_called_once()
        assert agent._initialized is False

    async def test_shutdown_without_memory_manager(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        agent._memory_manager = None

        # Must not raise
        await agent.shutdown()
        assert agent._initialized is False

    async def test_shutdown_swallows_close_exception(self) -> None:
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()

        mock_mgr = AsyncMock()
        mock_mgr.close = AsyncMock(side_effect=RuntimeError("close error"))
        agent._memory_manager = mock_mgr

        # Must not raise
        await agent.shutdown()
        assert agent._initialized is False


# ---------------------------------------------------------------------------
# Tests: initialize() — LLM auto-creation path
# ---------------------------------------------------------------------------

class TestInitializeAutoLLM:
    async def test_llm_created_from_registry_when_not_provided(self) -> None:
        """When llm_provider=None, initialize() must call get_provider()."""
        mock_llm = AsyncMock()
        mock_llm.complete = AsyncMock(return_value=_assistant_final("auto"))

        with patch("hivecore.core.agent.get_provider", return_value=mock_llm):
            agent = Agent()
            await agent.initialize()

        assert agent._llm is mock_llm

    async def test_initialize_is_idempotent(self) -> None:
        """Calling initialize() twice must not duplicate the system message."""
        llm = _make_llm_sequence(_assistant_final("ok"))
        agent = Agent(llm_provider=llm)
        await agent.initialize()
        msg_count_after_first = len(agent._conversation.messages)

        await agent.initialize()  # second call should be a no-op
        assert len(agent._conversation.messages) == msg_count_after_first
