"""Prompt builder for constructing dynamic system prompts.

Assembles the system prompt by combining persona, tool descriptions,
and relevant memory context.
"""

from __future__ import annotations

from hivecore.config.defaults import REACT_SYSTEM_TEMPLATE
from hivecore.core.tools.base import ToolDefinition


def build_system_prompt(
    agent_name: str = "HiveCore",
    persona_prompt: str = "",
    tools: list[ToolDefinition] | None = None,
    memory_context: str = "",
) -> str:
    """Build the complete system prompt for the agent.

    Args:
        agent_name: The agent's display name.
        persona_prompt: The active persona's system prompt.
        tools: List of available tool definitions.
        memory_context: Retrieved memory context to inject.

    Returns:
        The fully assembled system prompt string.
    """
    tool_descriptions = _format_tool_descriptions(tools or [])

    return REACT_SYSTEM_TEMPLATE.format(
        agent_name=agent_name,
        persona_prompt=persona_prompt,
        tool_descriptions=tool_descriptions if tool_descriptions else "No tools available.",
        memory_context=memory_context if memory_context else "No relevant memory found.",
        tool_name="tool_name",
    )


def _format_tool_descriptions(tools: list[ToolDefinition]) -> str:
    """Format tool definitions into a readable description block."""
    if not tools:
        return ""

    lines = []
    for tool in tools:
        params_str = ", ".join(
            f"{p.name}: {p.type}" + ("" if p.required else f" = {p.default}")
            for p in tool.parameters
        )
        lines.append(f"### {tool.name}")
        lines.append(f"  Description: {tool.description}")
        lines.append(f"  Parameters: ({params_str})")
        if tool.requires_confirmation:
            lines.append("  [Requires user confirmation before execution]")
        lines.append("")

    return "\n".join(lines)
