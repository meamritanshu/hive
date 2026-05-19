"""Base tool interface and decorators.

Defines the Tool abstraction and the @tool decorator for creating
tools from plain Python functions.
"""

from __future__ import annotations

import abc
import inspect
import json
import logging
from collections.abc import Callable
from typing import Any, get_type_hints

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any | None = None
    enum: list[str] | None = None


class ToolDefinition(BaseModel):
    """Complete tool definition used for LLM function calling."""

    name: str = Field(description="Unique tool name.")
    description: str = Field(description="What this tool does.")
    parameters: list[ToolParameter] = Field(default_factory=list)
    category: str = Field(default="general", description="Tool category.")
    requires_confirmation: bool = Field(
        default=False, description="Whether to ask user before executing."
    )

    def to_openai_schema(self) -> dict[str, Any]:
        """Convert to OpenAI function calling format.

        Returns:
            Dict in the OpenAI tools schema format.
        """
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": _python_type_to_json(param.type),
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


class BaseTool(abc.ABC):
    """Abstract base class for tools.

    Tools can be created by subclassing BaseTool or by using the @tool decorator.
    """

    @abc.abstractmethod
    def get_definition(self) -> ToolDefinition:
        """Return the tool's definition for LLM registration."""
        ...

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            String result of the tool execution.
        """
        ...

    @property
    def name(self) -> str:
        return self.get_definition().name

    @property
    def description(self) -> str:
        return self.get_definition().description


class FunctionTool(BaseTool):
    """Wraps a plain Python function as a Tool.

    Created automatically by the @tool decorator.
    """

    def __init__(
        self,
        func: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
        category: str = "general",
        requires_confirmation: bool = False,
    ) -> None:
        self._func = func
        self._name = name or func.__name__
        self._description = description or func.__doc__ or f"Execute {self._name}"
        self._category = category
        self._requires_confirmation = requires_confirmation
        self._definition = self._build_definition()

    def _build_definition(self) -> ToolDefinition:
        """Build a ToolDefinition from the function's signature and type hints."""
        sig = inspect.signature(self._func)
        hints = get_type_hints(self._func)
        params: list[ToolParameter] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            ptype = hints.get(param_name, str)
            if hasattr(ptype, "__name__"):
                param_type = ptype.__name__
            elif hasattr(ptype, "__origin__") and hasattr(ptype.__origin__, "__name__"):
                param_type = ptype.__origin__.__name__
            else:
                param_type = str(ptype).replace("typing.", "")

            has_default = param.default is not inspect.Parameter.empty

            # Try to extract description from docstring
            desc = _extract_param_doc(self._func, param_name)

            params.append(
                ToolParameter(
                    name=param_name,
                    type=param_type,
                    description=desc,
                    required=not has_default,
                    default=param.default if has_default else None,
                )
            )

        return ToolDefinition(
            name=self._name,
            description=self._description.strip(),
            parameters=params,
            category=self._category,
            requires_confirmation=self._requires_confirmation,
        )

    def get_definition(self) -> ToolDefinition:
        return self._definition

    async def execute(self, **kwargs: Any) -> str:
        """Execute the wrapped function.

        Raises:
            Exception: Any exception raised by the wrapped function is
                re-raised so that callers (e.g. ``Agent._execute_tool``)
                can record it in ``ToolResult.error`` and apply retry /
                reflection logic.
        """
        if inspect.iscoroutinefunction(self._func):
            result = await self._func(**kwargs)
        else:
            result = self._func(**kwargs)

        if isinstance(result, str):
            return result
        return json.dumps(result, default=str, indent=2)


def tool(
    name: str | None = None,
    description: str | None = None,
    category: str = "general",
    requires_confirmation: bool = False,
) -> Callable:
    """Decorator to create a Tool from a Python function.

    Usage:
        @tool(name="search_web", description="Search the web for information")
        def search_web(query: str) -> str:
            ...

    Args:
        name: Tool name (defaults to function name).
        description: Tool description (defaults to docstring).
        category: Tool category for grouping.
        requires_confirmation: Whether to ask user before executing.

    Returns:
        A FunctionTool instance wrapping the decorated function.
    """
    def decorator(func: Callable) -> FunctionTool:
        return FunctionTool(
            func=func,
            name=name,
            description=description,
            category=category,
            requires_confirmation=requires_confirmation,
        )
    return decorator


def _python_type_to_json(type_name: str) -> str:
    """Map Python type names to JSON Schema types."""
    mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
        "NoneType": "null",
    }
    return mapping.get(type_name, "string")


def _extract_param_doc(func: Callable, param_name: str) -> str:
    """Extract parameter documentation from a function's docstring.

    Looks for Google-style or numpy-style docstring parameter descriptions.
    """
    doc = func.__doc__
    if not doc:
        return f"Parameter: {param_name}"

    lines = doc.split("\n")
    in_args_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.lower() in ("args:", "arguments:", "parameters:"):
            in_args_section = True
            continue
        if in_args_section:
            if stripped.startswith(f"{param_name}:") or stripped.startswith(f"{param_name} ("):
                # Extract description after the colon
                if ":" in stripped:
                    parts = stripped.split(":", 1)
                    if len(parts) > 1:
                        return parts[1].strip()
            elif stripped and not stripped.startswith(" ") and ":" not in stripped:
                # Left the args section
                in_args_section = False

    return f"Parameter: {param_name}"
