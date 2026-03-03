"""Interactive chat session for the CLI."""

from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.prompt import Prompt

console = Console()


async def interactive_chat(
    message: Optional[str] = None,
    model_override: Optional[str] = None,
) -> None:
    """Run an interactive chat session with the agent.

    Args:
        message: Optional initial message. If provided, sends it and exits.
        model_override: Optional model override for the LLM provider.
    """
    from hivecore.config.settings import get_settings
    from hivecore.core.agent import Agent

    settings = get_settings()
    if model_override:
        settings.llm.model = model_override

    agent = Agent(settings=settings)
    await agent.initialize()

    console.print("[bold blue]HiveCore[/bold blue] Interactive Chat")
    console.print("Type [bold]exit[/bold] or [bold]quit[/bold] to end the session.")
    console.print("Type [bold]/clear[/bold] to clear conversation history.")
    console.print("Type [bold]/memory[/bold] to show memory stats.")
    console.print("---")

    if message:
        # Single-shot mode
        response = await agent.run(message)
        console.print(Markdown(response.content))
        return

    # Interactive loop
    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input.strip():
            continue

        if user_input.strip().lower() in ("exit", "quit"):
            console.print("[dim]Goodbye![/dim]")
            break

        if user_input.strip() == "/clear":
            await agent.clear_conversation()
            console.print("[dim]Conversation cleared.[/dim]")
            continue

        if user_input.strip() == "/memory":
            stats = await agent.memory_stats()
            console.print(stats)
            continue

        # Stream the response
        console.print("[bold blue]HiveCore[/bold blue]: ", end="")
        full_response = ""
        async for chunk in agent.run_stream(user_input):
            console.print(chunk, end="")
            full_response += chunk
        console.print()  # newline after streaming

    await agent.shutdown()
