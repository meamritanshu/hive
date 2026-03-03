"""Tests for the tool system."""

import json

import pytest

from hivecore.core.tools.base import FunctionTool, ToolDefinition, ToolParameter, tool
from hivecore.core.tools.registry import ToolRegistry


class TestToolDefinition:
    """Tests for ToolDefinition."""

    def test_basic_definition(self) -> None:
        defn = ToolDefinition(
            name="test_tool",
            description="A test tool",
            parameters=[
                ToolParameter(name="query", type="str", description="Search query"),
            ],
        )
        assert defn.name == "test_tool"
        assert len(defn.parameters) == 1

    def test_to_openai_schema(self) -> None:
        defn = ToolDefinition(
            name="search",
            description="Search the web",
            parameters=[
                ToolParameter(name="query", type="str", description="Search query", required=True),
                ToolParameter(name="limit", type="int", description="Max results", required=False, default=5),
            ],
        )
        schema = defn.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "search"
        assert "query" in schema["function"]["parameters"]["properties"]
        assert "query" in schema["function"]["parameters"]["required"]
        assert "limit" not in schema["function"]["parameters"]["required"]


class TestFunctionTool:
    """Tests for FunctionTool."""

    def test_sync_function_tool(self) -> None:
        def add(a: int, b: int) -> int:
            """Add two numbers.

            Args:
                a: First number.
                b: Second number.
            """
            return a + b

        ft = FunctionTool(func=add, name="add", description="Add two numbers")
        defn = ft.get_definition()
        assert defn.name == "add"
        assert len(defn.parameters) == 2
        assert defn.parameters[0].name == "a"
        assert defn.parameters[0].type == "int"

    @pytest.mark.asyncio
    async def test_sync_function_execution(self) -> None:
        def multiply(x: int, y: int) -> int:
            return x * y

        ft = FunctionTool(func=multiply, name="multiply")
        result = await ft.execute(x=3, y=4)
        assert result == "12"

    @pytest.mark.asyncio
    async def test_async_function_execution(self) -> None:
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        ft = FunctionTool(func=greet, name="greet")
        result = await ft.execute(name="World")
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_function_error_handling(self) -> None:
        def failing_func(x: int) -> int:
            raise ValueError("Something went wrong")

        ft = FunctionTool(func=failing_func, name="fail")
        with pytest.raises(ValueError, match="Something went wrong"):
            await ft.execute(x=1)


class TestToolDecorator:
    """Tests for the @tool decorator."""

    def test_decorator_creates_function_tool(self) -> None:
        @tool(name="my_tool", description="Test tool")
        def my_func(arg: str) -> str:
            return arg

        # The decorator returns a FunctionTool, not a Skill
        # (the @tool decorator from tools.base, not skills.base)
        assert isinstance(my_func, FunctionTool)
        assert my_func.name == "my_tool"


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_and_get(self) -> None:
        registry = ToolRegistry()

        def dummy(x: str) -> str:
            return x

        ft = FunctionTool(func=dummy, name="dummy")
        registry.register(ft)

        assert "dummy" in registry
        assert registry.get("dummy") is ft

    def test_list_names(self) -> None:
        registry = ToolRegistry()
        for name in ["alpha", "beta", "gamma"]:
            def func(x: str) -> str:
                return x
            registry.register(FunctionTool(func=func, name=name))

        names = registry.list_names()
        assert names == ["alpha", "beta", "gamma"]

    def test_unregister(self) -> None:
        registry = ToolRegistry()

        def dummy(x: str) -> str:
            return x

        registry.register(FunctionTool(func=dummy, name="to_remove"))
        assert "to_remove" in registry

        result = registry.unregister("to_remove")
        assert result is True
        assert "to_remove" not in registry

    def test_get_openai_schemas(self) -> None:
        registry = ToolRegistry()

        def search(query: str) -> str:
            """Search the web."""
            return query

        registry.register(FunctionTool(func=search, name="search", description="Search"))
        schemas = registry.get_openai_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "search"

    def test_register_function_shorthand(self) -> None:
        registry = ToolRegistry()

        def helper(text: str) -> str:
            return text.upper()

        ft = registry.register_function(helper, name="upper")
        assert isinstance(ft, FunctionTool)
        assert "upper" in registry
