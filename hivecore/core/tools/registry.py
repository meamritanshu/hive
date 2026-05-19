"""Tool registry for managing and discovering tools.

Provides a central registry where tools are registered and can be
looked up by name for the agent's ReAct loop.
"""

from __future__ import annotations

import logging
from typing import Any

from hivecore.core.tools.base import BaseTool, FunctionTool, ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Central registry for all available tools.

    The agent uses this registry to:
    1. Get tool definitions for LLM function calling
    2. Look up tools by name for execution
    3. Manage tool lifecycle
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool.

        Args:
            tool: The tool to register.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        name = tool.name
        if name in self._tools:
            logger.warning("Tool '%s' is being overwritten in registry", name)
        self._tools[name] = tool
        logger.debug("Registered tool: %s", name)

    def register_function(
        self,
        func: Any,
        name: str | None = None,
        description: str | None = None,
        category: str = "general",
    ) -> FunctionTool:
        """Register a plain function as a tool.

        Args:
            func: The function to register.
            name: Optional tool name (defaults to function name).
            description: Optional description.
            category: Tool category.

        Returns:
            The created FunctionTool.
        """
        tool = FunctionTool(func=func, name=name, description=description, category=category)
        self.register(tool)
        return tool

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name.

        Args:
            name: The tool name.

        Returns:
            The tool, or None if not found.
        """
        return self._tools.get(name)

    def get_definitions(self) -> list[ToolDefinition]:
        """Get definitions for all registered tools.

        Returns:
            List of ToolDefinition objects.
        """
        return [tool.get_definition() for tool in self._tools.values()]

    def get_openai_schemas(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI function calling format.

        Returns:
            List of dicts in OpenAI tools schema format.
        """
        return [defn.to_openai_schema() for defn in self.get_definitions()]

    def list_names(self) -> list[str]:
        """List all registered tool names."""
        return sorted(self._tools.keys())

    def list_by_category(self) -> dict[str, list[str]]:
        """Group tool names by category."""
        categories: dict[str, list[str]] = {}
        for tool in self._tools.values():
            cat = tool.get_definition().category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tool.name)
        return categories

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.

        Args:
            name: Tool name to remove.

        Returns:
            True if the tool was removed, False if not found.
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug("Unregistered tool: %s", name)
            return True
        return False

    def clear(self) -> None:
        """Remove all registered tools."""
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
