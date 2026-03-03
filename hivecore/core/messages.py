"""Message schema for HiveCore.

Defines the standard message format used throughout the framework
for communication between the agent, LLM, tools, memory, and channels.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    """Message role types."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolCall(BaseModel):
    """Represents a tool/function call request from the LLM."""

    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")
    name: str = Field(description="Tool/function name to call.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments to pass to the tool."
    )


class ToolResult(BaseModel):
    """Result from executing a tool."""

    call_id: str = Field(description="ID of the original tool call.")
    name: str = Field(description="Name of the tool that was executed.")
    output: str = Field(description="Tool execution output.")
    error: Optional[str] = Field(default=None, description="Error message if execution failed.")
    execution_time: float = Field(default=0.0, description="Execution time in seconds.")


class Message(BaseModel):
    """Standard message format used across HiveCore.

    This is the universal message schema used for:
    - Conversations between user and agent
    - LLM API calls
    - Tool calls and results
    - Memory storage
    - Channel message routing
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    role: Role = Field(description="The role of the message sender.")
    content: str = Field(default="", description="Text content of the message.")
    tool_calls: list[ToolCall] = Field(
        default_factory=list, description="Tool calls requested by the assistant."
    )
    tool_result: Optional[ToolResult] = Field(
        default=None, description="Result from a tool execution."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (timestamps, channel info, etc.).",
    )
    timestamp: float = Field(
        default_factory=time.time, description="Unix timestamp of message creation."
    )

    @classmethod
    def system(cls, content: str) -> Message:
        """Create a system message."""
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str, **metadata: Any) -> Message:
        """Create a user message."""
        return cls(role=Role.USER, content=content, metadata=metadata)

    @classmethod
    def assistant(cls, content: str, tool_calls: Optional[list[ToolCall]] = None) -> Message:
        """Create an assistant message."""
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls or [])

    @classmethod
    def tool(cls, result: ToolResult) -> Message:
        """Create a tool result message."""
        return cls(role=Role.TOOL, content=result.output, tool_result=result)

    def to_llm_format(self) -> dict[str, Any]:
        """Convert to the format expected by LiteLLM/OpenAI API.

        Returns:
            Dict compatible with OpenAI chat completion message format.
        """
        msg: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }

        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _serialize_arguments(tc.arguments),
                    },
                }
                for tc in self.tool_calls
            ]

        if self.role == Role.TOOL and self.tool_result:
            msg["tool_call_id"] = self.tool_result.call_id
            msg["name"] = self.tool_result.name

        return msg

    @property
    def token_estimate(self) -> int:
        """Rough token count estimate (4 chars ~= 1 token)."""
        text = self.content
        if self.tool_calls:
            import json
            text += json.dumps([tc.model_dump() for tc in self.tool_calls])
        return len(text) // 4


def _serialize_arguments(args: dict[str, Any]) -> str:
    """Serialize tool call arguments to JSON string."""
    import json
    return json.dumps(args)


class Conversation(BaseModel):
    """A conversation consisting of a sequence of messages."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    messages: list[Message] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)

    def add(self, message: Message) -> None:
        """Add a message to the conversation."""
        self.messages.append(message)

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """Get all messages in LLM-compatible format."""
        return [m.to_llm_format() for m in self.messages]

    @property
    def total_token_estimate(self) -> int:
        """Estimate total tokens in the conversation."""
        return sum(m.token_estimate for m in self.messages)

    def last_n(self, n: int) -> list[Message]:
        """Get the last N messages."""
        return self.messages[-n:] if n < len(self.messages) else self.messages.copy()

    def clear(self) -> None:
        """Clear all messages except system messages."""
        self.messages = [m for m in self.messages if m.role == Role.SYSTEM]
