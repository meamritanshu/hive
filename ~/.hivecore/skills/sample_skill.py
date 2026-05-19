from hivecore.skills.base import skill

@skill(
    name="sample_greeting",
    description="A sample skill that greets the user.",
    parameters=[
        {
            "name": "name",
            "type": "string",
            "description": "The name of the user to greet.",
            "required": True
        }
    ]
)
async def sample_greeting(name: str) -> str:
    """Returns a greeting message for the specified name."""
    return f"Hello, {name}! This is a dynamically loaded skill from HiveCore."
