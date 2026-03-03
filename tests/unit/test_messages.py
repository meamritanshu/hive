"""Tests for the message schema."""

import time

from hivecore.core.messages import Conversation, Message, Role, ToolCall, ToolResult


class TestMessage:
    """Tests for the Message class."""

    def test_create_user_message(self) -> None:
        msg = Message.user("Hello, agent!")
        assert msg.role == Role.USER
        assert msg.content == "Hello, agent!"
        assert msg.id  # should have an auto-generated ID
        assert msg.timestamp > 0

    def test_create_assistant_message(self) -> None:
        msg = Message.assistant("I can help with that.")
        assert msg.role == Role.ASSISTANT
        assert msg.content == "I can help with that."

    def test_create_system_message(self) -> None:
        msg = Message.system("You are a helpful assistant.")
        assert msg.role == Role.SYSTEM
        assert msg.content == "You are a helpful assistant."

    def test_create_tool_message(self) -> None:
        result = ToolResult(
            call_id="call_123",
            name="search",
            output="Found 5 results",
            execution_time=0.5,
        )
        msg = Message.tool(result)
        assert msg.role == Role.TOOL
        assert msg.content == "Found 5 results"
        assert msg.tool_result is not None
        assert msg.tool_result.call_id == "call_123"

    def test_message_with_tool_calls(self) -> None:
        tool_calls = [
            ToolCall(name="search", arguments={"query": "python"}),
            ToolCall(name="calculate", arguments={"expression": "2+2"}),
        ]
        msg = Message.assistant("Let me search and calculate.", tool_calls=tool_calls)
        assert len(msg.tool_calls) == 2
        assert msg.tool_calls[0].name == "search"
        assert msg.tool_calls[1].arguments == {"expression": "2+2"}

    def test_to_llm_format_user(self) -> None:
        msg = Message.user("Hello")
        fmt = msg.to_llm_format()
        assert fmt["role"] == "user"
        assert fmt["content"] == "Hello"

    def test_to_llm_format_with_tool_calls(self) -> None:
        tc = ToolCall(id="tc_1", name="search", arguments={"q": "test"})
        msg = Message.assistant("Searching...", tool_calls=[tc])
        fmt = msg.to_llm_format()
        assert fmt["role"] == "assistant"
        assert len(fmt["tool_calls"]) == 1
        assert fmt["tool_calls"][0]["function"]["name"] == "search"

    def test_to_llm_format_tool_result(self) -> None:
        result = ToolResult(call_id="tc_1", name="search", output="results here")
        msg = Message.tool(result)
        fmt = msg.to_llm_format()
        assert fmt["role"] == "tool"
        assert fmt["tool_call_id"] == "tc_1"
        assert fmt["name"] == "search"

    def test_token_estimate(self) -> None:
        msg = Message.user("This is a test message with some words")
        assert msg.token_estimate > 0
        # ~40 chars / 4 = ~10 tokens
        assert msg.token_estimate >= 5


class TestConversation:
    """Tests for the Conversation class."""

    def test_empty_conversation(self) -> None:
        conv = Conversation()
        assert len(conv.messages) == 0
        assert conv.total_token_estimate == 0

    def test_add_messages(self) -> None:
        conv = Conversation()
        conv.add(Message.system("You are helpful."))
        conv.add(Message.user("Hello"))
        conv.add(Message.assistant("Hi there!"))
        assert len(conv.messages) == 3

    def test_get_messages_for_llm(self) -> None:
        conv = Conversation()
        conv.add(Message.system("System prompt"))
        conv.add(Message.user("User message"))
        llm_messages = conv.get_messages_for_llm()
        assert len(llm_messages) == 2
        assert llm_messages[0]["role"] == "system"
        assert llm_messages[1]["role"] == "user"

    def test_last_n(self) -> None:
        conv = Conversation()
        for i in range(10):
            conv.add(Message.user(f"Message {i}"))
        last_3 = conv.last_n(3)
        assert len(last_3) == 3
        assert last_3[0].content == "Message 7"

    def test_clear_keeps_system(self) -> None:
        conv = Conversation()
        conv.add(Message.system("Keep me"))
        conv.add(Message.user("Remove me"))
        conv.add(Message.assistant("Remove me too"))
        conv.clear()
        assert len(conv.messages) == 1
        assert conv.messages[0].role == Role.SYSTEM
