# HiveCore — Getting Started

## Requirements

- Python 3.10 or later
- pip

---

## Installation

```bash
pip install hivecore
```

For optional features:

```bash
pip install hivecore[chromadb]        # ChromaDB vector store
pip install hivecore[discord]         # Discord bot channel
pip install hivecore[telegram]        # Telegram bot channel
pip install hivecore[embeddings-local]# Local sentence-transformers embeddings
pip install hivecore[all]             # Everything above
```

---

## Quick Start

### 1. Set your LLM API key

```bash
export OPENAI_API_KEY=sk-...
```

Or for any other LiteLLM-supported provider (Anthropic, Gemini, etc.):

```bash
export ANTHROPIC_API_KEY=...
export GEMINI_API_KEY=...
```

### 2. Start the workstation

```bash
hivecore start
```

This starts the web server at `http://127.0.0.1:8088`, the scheduler, and any configured channels.

### 3. Open the web console

Navigate to `http://127.0.0.1:8088` in your browser. You will see the Dashboard. Click **Chat** in the sidebar to start talking to your agent.

### 4. Or use the CLI chat

```bash
hivecore chat
```

Type your message and press Enter. Type `exit` or press `Ctrl+C` to quit.

---

## Configuration

HiveCore creates `~/.hivecore/config.toml` on first run. You can edit it directly or use the CLI.

### View current config

```bash
hivecore config
```

### Common settings

**Switch to a local Ollama model:**

```toml
[llm]
provider = "ollama"
model = "llama3"
api_base = "http://localhost:11434"
```

**Use Claude:**

```toml
[llm]
provider = "anthropic"
model = "claude-3-5-sonnet-20241022"
api_key = "sk-ant-..."
```

**Use Gemini:**

```toml
[llm]
provider = "google"
model = "gemini/gemini-1.5-pro"
api_key = "..."
```

**Change the web server port:**

```toml
[web]
host = "127.0.0.1"
port = 9000
```

**Change the agent persona:**

```toml
[agent]
persona = "assistant"       # options: default, assistant, researcher, coder
system_prompt_extra = "Always respond in bullet points."
```

All settings can also be set via environment variables with the `HIVECORE_` prefix. For nested settings, use double underscores:

```bash
export HIVECORE_LLM__MODEL=gpt-4o-mini
export HIVECORE_WEB__PORT=9000
```

---

## Memory

The agent automatically remembers things you tell it across sessions. Memories are stored as Markdown files under `~/.hivecore/memory/` and are fully human-readable and editable.

### Search memory from the CLI (coming soon via web console)

Open the **Memory** page in the web console at `http://127.0.0.1:8088/memory`. Use the search bar to find past memories.

### Memory types

| Type | What gets stored there |
|---|---|
| Personal | Facts about you (name, preferences, location, etc.) |
| Task | Active projects and tasks |
| Tool | Notes about how tools and skills work |
| Episodic | Conversation logs by day |

### Edit memory directly

Memory files are plain Markdown. You can open and edit them in any text editor:

```
~/.hivecore/memory/knowledge/personal.md
~/.hivecore/memory/knowledge/tasks.md
~/.hivecore/memory/daily/2026-03-04.md
```

### Use ChromaDB instead of SQLite

```toml
[memory]
vector_store = "chromadb"
```

Requires `pip install hivecore[chromadb]`.

### Use local embeddings (no API key needed)

```toml
[memory]
embedding_provider = "local"
embedding_model = "all-MiniLM-L6-v2"
```

Requires `pip install hivecore[embeddings-local]`.

---

## Skills

Skills are Python functions that extend what your agent can do. They live in `~/.hivecore/skills/` and are auto-discovered at startup.

### Create a skill

Create a file at `~/.hivecore/skills/my_skill.py`:

```python
from hivecore.skills.base import skill

@skill(
    name="greet_user",
    description="Greet a user by name",
    parameters=[
        {"name": "name", "type": "string", "description": "The user's name", "required": True}
    ],
)
async def greet_user(name: str) -> str:
    return f"Hello, {name}! Welcome to HiveCore."
```

Save the file. HiveCore picks it up automatically (no restart needed if `hot_reload = true`).

### List installed skills

```bash
hivecore skill list
```

Or open `http://127.0.0.1:8088/skills` in the web console.

### Schedule a skill

Add a cron expression to the `@skill` decorator:

```python
@skill(
    name="morning_briefing",
    description="Send a morning briefing",
    parameters=[],
    schedule="0 8 * * *",    # every day at 8:00 AM
)
async def morning_briefing() -> str:
    return "Good morning! Here is your briefing..."
```

Or add a job manually via the CLI:

```bash
hivecore schedule add --name "morning_briefing" --skill morning_briefing --cron "0 8 * * *"
```

### The built-in news_digest skill

```bash
# Ask the agent to use it:
hivecore chat
> Summarize today's news about artificial intelligence
```

Or call it directly (if you have the agent invoke it):

Parameters: `topic` (string), `count` (int, default 5).

---

## Scheduling

### List scheduled jobs

```bash
hivecore schedule list
```

Or open `http://127.0.0.1:8088/scheduler`.

### Add a job

```bash
hivecore schedule add \
  --name "daily-digest" \
  --skill news_digest \
  --cron "0 7 * * *"
```

### Remove a job

```bash
hivecore schedule remove <job-id>
```

### Cron expression format

Standard 5-field cron: `minute hour day-of-month month day-of-week`

| Expression | Meaning |
|---|---|
| `0 9 * * *` | Every day at 9:00 AM |
| `0 9 * * 1` | Every Monday at 9:00 AM |
| `*/30 * * * *` | Every 30 minutes |
| `0 8,12,18 * * *` | At 8 AM, noon, and 6 PM daily |

Timezone is set in `config.toml`:

```toml
[scheduler]
timezone = "America/New_York"
```

---

## Channels

### Discord

1. Create a Discord bot at https://discord.com/developers/applications
2. Copy the bot token
3. Add to `config.toml`:

```toml
[channels]
discord_token = "your-bot-token-here"
```

4. Install the extra and restart:

```bash
pip install hivecore[discord]
hivecore start
```

The bot responds to `@mentions` and direct messages.

### Telegram

1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. Copy the bot token
3. Add to `config.toml`:

```toml
[channels]
telegram_token = "your-bot-token-here"
```

4. Install the extra and restart:

```bash
pip install hivecore[telegram]
hivecore start
```

Send `/chat your message here` or a direct message to your bot.

---

## API Usage

The REST API is available while the workstation is running.

### Check status

```bash
curl http://127.0.0.1:8088/api/status
```

### Send a chat message

```bash
curl -X POST http://127.0.0.1:8088/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it?", "conversation_id": null}'
```

### Search memory

```bash
curl "http://127.0.0.1:8088/api/memory/search?q=python&top_k=5"
```

### List skills

```bash
curl http://127.0.0.1:8088/api/skills
```

### WebSocket streaming chat (example with websocat)

```bash
echo '{"message": "Tell me a joke", "conversation_id": null}' \
  | websocat ws://127.0.0.1:8088/ws/chat
```

---

## Check Workstation Status

```bash
hivecore status
```

This shows: running state, active LLM provider and model, memory stats, loaded skills, and active channels.

---

## Development Setup

```bash
git clone <repo>
cd <repo>
pip install -e ".[dev]"

# Run tests
pytest tests/unit/

# Build the frontend
cd frontend
npm install
npm run build
```

### Run in development mode (with live frontend reload)

Terminal 1 — API server:
```bash
hivecore start
```

Terminal 2 — Frontend dev server (proxies API to port 8088):
```bash
cd frontend
npm run dev
```

Then open `http://localhost:5173`.

---

## Directory Reference

```
~/.hivecore/
├── config.toml                  # All user settings
├── memory/
│   ├── MEMORY.md                # Top-level memory summary
│   ├── daily/YYYY-MM-DD.md      # Daily episodic logs
│   └── knowledge/
│       ├── personal.md
│       ├── tasks.md
│       └── tools.md
├── skills/                      # Drop .py skill files here
└── vectors.db                   # SQLite vector store
```

---

## Troubleshooting

**Agent returns errors about the LLM provider**  
Check that your API key environment variable is set and that the `model` name in config matches what your provider expects (LiteLLM format: `provider/model-name` for non-OpenAI providers).

**Skills are not being picked up**  
Ensure `hot_reload = true` in `[skills]` config, or restart `hivecore start`. Check that your skill file has no Python syntax errors.

**Port 8088 is already in use**  
Change the port in `config.toml` under `[web] port = 9000`.

**Memory search returns no results**  
The vector store is empty until the agent has had a few conversations. For immediate results, you can manually add text to the Markdown files under `~/.hivecore/memory/knowledge/`.

**ChromaDB import error**  
Run `pip install hivecore[chromadb]` and ensure `vector_store = "chromadb"` is in your `[memory]` config.
