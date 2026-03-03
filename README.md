<p align="center">
  <img src="hivecore/web/static/hive.svg" alt="HiveCore Logo" width="120" />
</p>

<h1 align="center">HiveCore</h1>

<p align="center">
  <strong>A local-first agentic workstation framework with long-term memory, extensible skills, scheduled automation, and multi-channel access.</strong>
</p>

<p align="center">
  <a href="#features">Features</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#skills">Skills</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#roadmap">Roadmap</a> •
  <a href="#contributing">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="License" />
  <img src="https://img.shields.io/badge/version-0.1.0-orange" alt="Version" />
  <img src="https://img.shields.io/badge/tests-352%20passed-brightgreen" alt="Tests" />
  <img src="https://img.shields.io/badge/coverage-80.84%25-brightgreen" alt="Coverage" />
</p>

---

## What is HiveCore?

HiveCore is a **privacy-focused personal AI agent** that runs entirely on your machine. It gives you a single intelligent agent with persistent memory, extensible skills, scheduled automation, and multiple ways to interact — web console, CLI, Discord, or Telegram.

### Design Philosophy

- **🏠 Local-first** — All data lives in `~/.hivecore/` as human-readable files. No cloud lock-in.
- **🔌 Extensible** — Drop a `.py` file into `~/.hivecore/skills/` to add new capabilities. No framework knowledge required.
- **🔒 Private** — Nothing leaves your machine unless you explicitly configure an external LLM provider.
- **🧠 Deeply capable** — One agent with long-term memory, scheduling, and tool use — not a fragile multi-agent mesh.

---

## Features

| Feature | Description |
|---------|-------------|
| **100+ LLM Providers** | OpenAI, Claude, Gemini, Ollama, OpenRouter, and more via [LiteLLM](https://github.com/BerriAI/litellm) |
| **Long-term Memory** | Tiered memory system — short-term, file-based Markdown, and vector search (SQLite/ChromaDB) |
| **Hybrid Retrieval** | BM25 keyword + vector similarity combined via Reciprocal Rank Fusion |
| **Extensible Skills** | Auto-discovered Python skills with hot-reload. No restart needed. |
| **Scheduled Automation** | Cron-based scheduling via APScheduler for recurring tasks |
| **Web Console** | React + TypeScript dashboard with chat, memory browser, skill manager, and scheduler |
| **Multi-Channel** | Interact via Web, CLI, Discord, or Telegram |
| **Git-Synced Memory** | Automatic git versioning of your memory files |
| **Sandboxed Execution** | Skills run in subprocess isolation (Docker support planned) |
| **ReAct Agent Loop** | Reason → Act → Observe loop with self-reflection on repeated failures |

---

## Quick Start

### 1. Install

```bash
pip install hivecore
```

### 2. Set your API key

```bash
export OPENAI_API_KEY=sk-...
# Or any LiteLLM-supported provider:
# export ANTHROPIC_API_KEY=...
# export GEMINI_API_KEY=...
```

### 3. Start the workstation

```bash
hivecore start
```

### 4. Open the web console

Navigate to **http://127.0.0.1:8088** — or use the CLI:

```bash
hivecore chat
```

### Optional extras

```bash
pip install hivecore[chromadb]          # ChromaDB vector store
pip install hivecore[discord]           # Discord bot channel
pip install hivecore[telegram]          # Telegram bot channel
pip install hivecore[embeddings-local]  # Local embeddings (no API key needed)
pip install hivecore[all]               # Everything above
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Access Channels                   │
│       Web Console · CLI · Discord · Telegram        │
├─────────────────────────────────────────────────────┤
│                 Layer 1 — HiveCore                  │
│    Agent (ReAct loop) · Tools · LLM Providers       │
├─────────────────────────────────────────────────────┤
│                Layer 2 — HiveRuntime                │
│   Executor · Scheduler · Heartbeat · Sandboxing     │
├─────────────────────────────────────────────────────┤
│                Layer 3 — HiveMemory                 │
│  Short-term · File Memory · Vector Memory · Hybrid  │
└─────────────────────────────────────────────────────┘
```

### Layer 1 — Agent Framework
The core reasoning engine using a **ReAct loop** (Reason → Act → Observe). Unified LLM access via LiteLLM. Built-in tools include file I/O, shell execution, web search, time, and math. Custom tools via `@tool` decorator.

### Layer 2 — Runtime
Manages lifecycle, task execution with metrics, APScheduler-based cron jobs, periodic heartbeat, and subprocess sandboxing for skill isolation.

### Layer 3 — Memory

| Component | Description |
|-----------|-------------|
| `ShortTermMemory` | Sliding window of the last 50 messages, in-process |
| `FileMemory` | Markdown files in `~/.hivecore/memory/` — human-readable and editable |
| `VectorMemory` | Embedding-based semantic search (SQLite default / ChromaDB optional) |
| `HybridRetriever` | BM25 + vector similarity via Reciprocal Rank Fusion |
| `MemoryCompactor` | Tiered summarization: raw → weekly summary → entity extraction |

---

## Skills

Skills are Python functions that extend what your agent can do. Drop them into `~/.hivecore/skills/` and they're auto-discovered.

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

### Schedule a skill

```python
@skill(
    name="morning_briefing",
    description="Send a morning briefing",
    parameters=[],
    schedule="0 8 * * *",  # every day at 8:00 AM
)
async def morning_briefing() -> str:
    return "Good morning! Here is your briefing..."
```

Or via CLI:

```bash
hivecore schedule add --name "morning_briefing" --skill morning_briefing --cron "0 8 * * *"
```

---

## Configuration

HiveCore uses `~/.hivecore/config.toml` for all settings. Examples:

**Use a local Ollama model:**
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
```

**Use local embeddings (no API key):**
```toml
[memory]
embedding_provider = "local"
embedding_model = "all-MiniLM-L6-v2"
```

All settings can also be set via environment variables with the `HIVECORE_` prefix:
```bash
export HIVECORE_LLM__MODEL=gpt-4o-mini
export HIVECORE_WEB__PORT=9000
```

---

## API

The REST API is available while the workstation is running:

```bash
# Check status
curl http://127.0.0.1:8088/api/status

# Send a chat message
curl -X POST http://127.0.0.1:8088/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What time is it?", "conversation_id": null}'

# Search memory
curl "http://127.0.0.1:8088/api/memory/search?q=python&top_k=5"

# WebSocket streaming
echo '{"message": "Tell me a joke"}' | websocat ws://127.0.0.1:8088/ws/chat
```

---

## Data Layout

```
~/.hivecore/
├── config.toml                    # All settings, human-editable
├── memory/
│   ├── MEMORY.md                  # Top-level memory summary
│   ├── daily/
│   │   └── YYYY-MM-DD.md          # Daily episodic logs
│   └── knowledge/
│       ├── personal.md            # Personal facts about the user
│       ├── tasks.md               # Task and project context
│       └── tools.md               # Tool usage notes
├── skills/                        # Drop custom .py skills here
└── vectors.db                     # SQLite vector store (default)
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| LLM Interface | LiteLLM |
| Agent Loop | ReAct (custom implementation) |
| Web Backend | FastAPI + Uvicorn |
| Web Frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Vector Store | SQLite (default) / ChromaDB (optional) |
| Scheduler | APScheduler |
| Config | Pydantic Settings + TOML |
| CLI | Typer + Rich |
| Packaging | pyproject.toml (PEP 517) |

---

## Development

```bash
git clone https://github.com/meamritanshu/hive.git
cd hive
pip install -e ".[dev]"

# Run tests
pytest tests/unit/

# Run with coverage
pytest tests/ --cov=hivecore --cov-report=term-missing

# Build the frontend
cd frontend
npm install
npm run build
```

### Development mode (live reload)

**Terminal 1** — API server:
```bash
hivecore start
```

**Terminal 2** — Frontend dev server:
```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

---

## Roadmap

See [`FUTURE_ROADMAP.md`](FUTURE_ROADMAP.md) for the full roadmap. Highlights:

| Phase | Features | Version |
|-------|----------|---------|
| **Production Hardening** | Docker sandboxing, Multi-agent, MCP support | v0.2.0 |
| **Intelligence & UX** | Skill marketplace, Pipelines/DAGs, Event triggers, Agent personas | v0.3.0 |
| **Scale & Enterprise** | Kubernetes, Knowledge graphs, Observability dashboard | v0.4.0 |
| **Advanced AI** | Voice interaction, Multimodal, Self-healing, Small+Large model collab | v0.5.0+ |

---

## Contributing

We welcome contributions! To get started:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run the test suite (`pytest tests/`)
5. Commit and push (`git push origin feature/amazing-feature`)
6. Open a Pull Request

Please reference the [roadmap](FUTURE_ROADMAP.md) if working on planned features.

---

## License

This project is licensed under the **Apache License 2.0** — see the [pyproject.toml](pyproject.toml) for details.

---

<p align="center">
  Built with ❤️ by the HiveCore Team
</p>
