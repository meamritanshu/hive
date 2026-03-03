"""Main Agent class with ReAct reasoning loop.

The Agent is the central orchestrator that:
1. Receives user input
2. Retrieves relevant memory context
3. Constructs prompts with tool definitions
4. Runs a ReAct (Reason + Act) loop with the LLM
5. Executes tools and feeds results back
6. Stores conversation and learned information in memory
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, AsyncIterator, Optional

from hivecore.config.defaults import PERSONA_PROMPTS
from hivecore.config.settings import HiveSettings
from hivecore.core.llm.base import LLMProvider
from hivecore.core.llm.registry import get_provider
from hivecore.core.messages import Conversation, Message, Role, ToolCall, ToolResult
from hivecore.core.prompt.builder import build_system_prompt
from hivecore.core.tools.base import BaseTool
from hivecore.core.tools.builtin.tools import register_builtin_tools
from hivecore.core.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Agent:
    """The core HiveCore agent with ReAct reasoning.

    This agent implements a Think -> Act -> Observe loop:
    1. Think: The LLM reasons about what to do next
    2. Act: If a tool is needed, execute it
    3. Observe: Feed the tool result back and repeat

    The loop continues until the LLM provides a final answer
    or the max iteration limit is reached.
    """

    def __init__(
        self,
        settings: Optional[HiveSettings] = None,
        llm_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ) -> None:
        self.settings = settings or HiveSettings()
        self._llm = llm_provider
        self._tools = tool_registry or ToolRegistry()
        self._conversation = Conversation()
        self._memory_manager: Optional[Any] = None  # Initialized in initialize()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the agent and all its subsystems.

        Must be called before using the agent. Sets up:
        - LLM provider
        - Tool registry with built-in tools
        - Memory manager
        - System prompt
        """
        if self._initialized:
            return

        # Initialize LLM provider
        if self._llm is None:
            self._llm = get_provider(self.settings.llm)

        # Register built-in tools
        register_builtin_tools(self._tools)

        # Initialize memory manager
        try:
            from hivecore.memory.manager import MemoryManager
            self._memory_manager = MemoryManager(self.settings.memory)
            await self._memory_manager.initialize()
        except Exception as e:
            logger.warning("Memory manager initialization failed: %s. Running without memory.", e)
            self._memory_manager = None

        # Build and set system prompt
        persona_prompt = PERSONA_PROMPTS.get(
            self.settings.agent.persona,
            self.settings.agent.system_prompt,
        )

        system_prompt = build_system_prompt(
            agent_name="HiveCore",
            persona_prompt=persona_prompt,
            tools=self._tools.get_definitions(),
            memory_context="",
        )
        self._conversation.add(Message.system(system_prompt))

        self._initialized = True
        logger.info("Agent initialized with model=%s, tools=%d",
                     self.settings.llm.model, len(self._tools))

    async def run(self, user_input: str) -> Message:
        """Process a user message and return the agent's response.

        Runs the full ReAct loop: retrieves memory, reasons with the LLM,
        executes tools as needed, and returns the final answer.

        Args:
            user_input: The user's message text.

        Returns:
            The agent's final response as a Message.
        """
        if not self._initialized:
            await self.initialize()

        # Retrieve relevant memory context
        memory_context = await self._retrieve_memory(user_input)
        if memory_context:
            self._update_system_prompt(memory_context)

        # Add user message
        user_msg = Message.user(user_input)
        self._conversation.add(user_msg)

        # Run ReAct loop
        response = await self._react_loop()

        # Store in memory
        await self._store_memory(user_input, response.content)

        return response

    async def run_stream(self, user_input: str) -> AsyncIterator[str]:
        """Process a user message and stream the response.

        For the final response (no tool calls), streams tokens.
        For intermediate tool-calling steps, runs them silently
        and then streams the final answer.

        Args:
            user_input: The user's message text.

        Yields:
            Response text chunks.
        """
        if not self._initialized:
            await self.initialize()

        memory_context = await self._retrieve_memory(user_input)
        if memory_context:
            self._update_system_prompt(memory_context)

        user_msg = Message.user(user_input)
        self._conversation.add(user_msg)

        # Run ReAct loop -- for now, do the full loop then stream the final answer
        # In a more advanced version, we'd stream intermediate reasoning too
        response = await self._react_loop()

        # Stream the final response content
        for i in range(0, len(response.content), 4):
            yield response.content[i:i + 4]

        await self._store_memory(user_input, response.content)

    # Number of consecutive tool failures that triggers a self-reflection step.
    _REFLECTION_FAILURE_THRESHOLD: int = 3

    async def _react_loop(self) -> Message:
        """Execute the ReAct reasoning loop.

        Iterates:
        1. Send conversation to LLM
        2. If LLM returns tool calls, execute them
        3. Add tool results to conversation
        4. After _REFLECTION_FAILURE_THRESHOLD consecutive tool errors,
           inject a self-reflection prompt so the LLM can reason about
           why it is failing before continuing (Critic/self-correction step).
        5. Repeat until the LLM gives a final answer or max iterations.

        Returns:
            The final assistant Message.
        """
        assert self._llm is not None

        max_iterations = self.settings.agent.max_iterations
        tool_schemas = self._tools.get_openai_schemas() if len(self._tools) > 0 else None
        consecutive_failures = 0

        for iteration in range(max_iterations):
            logger.debug("ReAct iteration %d/%d", iteration + 1, max_iterations)

            # Get LLM response
            response = await self._llm.complete(
                messages=self._conversation.messages,
                tools=tool_schemas,
            )

            self._conversation.add(response)

            # If no tool calls, this is the final answer
            if not response.tool_calls:
                logger.debug("Agent produced final answer on iteration %d", iteration + 1)
                return response

            # Execute tool calls and track consecutive failures
            for tool_call in response.tool_calls:
                result = await self._execute_tool(tool_call)
                tool_msg = Message.tool(result)
                self._conversation.add(tool_msg)

                if result.error:
                    consecutive_failures += 1
                    logger.debug(
                        "Tool '%s' failed (%d consecutive): %s",
                        tool_call.name, consecutive_failures, result.error,
                    )
                else:
                    consecutive_failures = 0

            # Self-reflection / Critic step: if we've hit the threshold,
            # inject a meta-reasoning prompt before the next LLM call so
            # the model can diagnose the failure pattern and try a new approach.
            if consecutive_failures >= self._REFLECTION_FAILURE_THRESHOLD:
                logger.warning(
                    "Self-reflection triggered after %d consecutive tool failures",
                    consecutive_failures,
                )
                self._conversation.add(
                    Message.user(
                        f"[Self-Reflection] You have encountered {consecutive_failures} "
                        "consecutive tool failures. Before calling any more tools, "
                        "please reason carefully about WHY these calls are failing. "
                        "Consider: Are the arguments malformed? Is the tool the wrong "
                        "choice for this task? Is there a simpler approach that avoids "
                        "the failing tool entirely? State your diagnosis, then decide "
                        "how to proceed differently."
                    )
                )
                consecutive_failures = 0  # Reset after reflection is injected

        # Max iterations reached -- ask LLM for a summary
        logger.warning("Max ReAct iterations (%d) reached", max_iterations)
        self._conversation.add(
            Message.user("Please provide your best answer with the information gathered so far.")
        )
        final = await self._llm.complete(messages=self._conversation.messages)
        self._conversation.add(final)
        return final

    async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
        """Execute a single tool call.

        Args:
            tool_call: The tool call to execute.

        Returns:
            The result of the tool execution.
        """
        start_time = time.time()
        tool = self._tools.get(tool_call.name)

        if tool is None:
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                output="",
                error=f"Unknown tool: {tool_call.name}. Available: {', '.join(self._tools.list_names())}",
            )

        try:
            logger.debug("Executing tool: %s(%s)", tool_call.name, tool_call.arguments)
            output = await tool.execute(**tool_call.arguments)
            elapsed = time.time() - start_time

            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                output=output,
                execution_time=elapsed,
            )
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("Tool execution failed: %s - %s", tool_call.name, e)
            return ToolResult(
                call_id=tool_call.id,
                name=tool_call.name,
                output="",
                error=str(e),
                execution_time=elapsed,
            )

    async def _retrieve_memory(self, query: str) -> str:
        """Retrieve relevant memory context for a query.

        Args:
            query: The user's input to find relevant memories for.

        Returns:
            Formatted memory context string, or empty string if no memory.
        """
        if self._memory_manager is None:
            return ""

        try:
            memories = await self._memory_manager.retrieve(query)
            if not memories:
                return ""

            context_parts = []
            for mem in memories:
                context_parts.append(f"- [{mem.get('type', 'general')}] {mem.get('content', '')}")
            return "\n".join(context_parts)
        except Exception as e:
            logger.warning("Memory retrieval failed: %s", e)
            return ""

    async def _store_memory(self, user_input: str, response: str) -> None:
        """Store conversation turn in memory.

        Args:
            user_input: The user's message.
            response: The agent's response.
        """
        if self._memory_manager is None:
            return

        try:
            await self._memory_manager.store_conversation(
                user_message=user_input,
                assistant_message=response,
            )
        except Exception as e:
            logger.warning("Memory storage failed: %s", e)

    def _update_system_prompt(self, memory_context: str) -> None:
        """Update the system message with fresh memory context."""
        if not self._conversation.messages:
            return

        persona_prompt = PERSONA_PROMPTS.get(
            self.settings.agent.persona,
            self.settings.agent.system_prompt,
        )

        new_system = build_system_prompt(
            agent_name="HiveCore",
            persona_prompt=persona_prompt,
            tools=self._tools.get_definitions(),
            memory_context=memory_context,
        )

        # Replace the system message
        if self._conversation.messages[0].role == Role.SYSTEM:
            self._conversation.messages[0] = Message.system(new_system)

    def register_tool(self, tool: BaseTool) -> None:
        """Register an additional tool with the agent.

        Args:
            tool: The tool to register.
        """
        self._tools.register(tool)

    async def clear_conversation(self) -> None:
        """Clear the conversation history, keeping the system prompt."""
        self._conversation.clear()

    async def memory_stats(self) -> str:
        """Get memory system statistics.

        Returns:
            Formatted string with memory stats.
        """
        if self._memory_manager is None:
            return "Memory system not initialized."

        try:
            stats = await self._memory_manager.get_stats()
            return json.dumps(stats, indent=2)
        except Exception as e:
            return f"Error getting memory stats: {e}"

    async def shutdown(self) -> None:
        """Gracefully shut down the agent and its subsystems."""
        if self._memory_manager:
            try:
                await self._memory_manager.close()
            except Exception as e:
                logger.warning("Error closing memory manager: %s", e)

        self._initialized = False
        logger.info("Agent shut down.")
