# HiveCore — Project Overview

## What is HiveCore?

HiveCore is a local-first, privacy-focused personal AI agent workstation. It runs entirely on your machine (or your own server), stores all data locally, and gives you a single intelligent agent you can interact with via a web console, Discord, Telegram, or a CLI.

The design philosophy is:
- **Local-first**: All memory, config, and skills live in `~/.hivecore/` as human-readable files. No cloud lock-in.
- **Extensible**: Drop a `.py` file into `~/.hivecore/skills/` to add new capabilities. No framework knowledge required.
- **Private**: Nothing leaves your machine unless you explicitly configure an external LLM provider.
- **Single-agent, deeply capable**: One agent with long-term memory, scheduling, and tool use — rather than a fragile multi-agent mesh.

---

## Architecture

HiveCore is organized into three primary layers.

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

### Layer 1 — HiveCore (Agent Framework)

The core reasoning engine. The agent uses a **ReAct loop** (Reason → Act → Observe) to answer questions and complete tasks.

- **LLM interface**: Unified via [LiteLLM](https://github.com/BerriAI/litellm), supporting OpenAI, Anthropic, Google, Azure, Ollama, OpenRouter, Together AI, and 100+ other providers.
- **Tool system**: First-class tool use. Built-in tools include file I/O, shell execution, web search, time, and math. Custom tools can be added via the `@tool` decorator.
- **Prompt builder**: Injects memory context, persona, and tool definitions into every LLM request.

### Layer 2 — HiveRuntime (Execution Environment)

Manages the lifecycle of the workstation and how tasks are executed.

- **Executor**: Handles tool and skill invocations with execution metrics (latency, success/failure).
- **Scheduler**: APScheduler-based cron jobs. Define recurring tasks in config or via CLI.
- **Heartbeat**: Periodic background pulse — useful for proactive memory compaction and health checks.
- **Sandboxing**: Skills run in subprocess isolation to prevent runaway code from affecting the main process.

### Layer 3 — HiveMemory (Memory System)

A dual memory architecture that stores both human-readable and vector-searchable memories.

| Component | Description |
|---|---|
| `ShortTermMemory` | Sliding window of the last 50 messages, held in-process |
| `FileMemory` | Markdown files in `~/.hivecore/memory/` — readable and editable by humans |
| `VectorMemory` | Embedding-based semantic search backed by SQLite (default) or ChromaDB |
| `HybridRetriever` | Combines BM25 keyword search + vector similarity (0.3/0.7 weight) via Reciprocal Rank Fusion |
| `MemoryCompactor` | Periodically summarizes old episodic memories to keep context windows manageable |

Memory is organized into four types: **Personal**, **Task**, **Tool**, and **Episodic**.

---

## Key Features

- **Multi-provider LLM support**: Works with local models (Ollama, llama.cpp), OpenAI, Claude, Gemini, and many more.
- **Long-term memory**: The agent remembers things across sessions, stored as readable Markdown.
- **Skill system**: Python skills are auto-discovered from `~/.hivecore/skills/`. Hot-reload is supported — no restart needed.
- **Scheduled automation**: Define cron jobs that run skills or agent prompts on a schedule.
- **Web console**: Full React + TypeScript dashboard at `http://127.0.0.1:8088` with chat, memory browser, skill manager, scheduler, and config viewer.
- **Multi-channel**: Chat with your agent via Discord or Telegram in addition to the web and CLI.
- **pip installable**: `pip install hivecore` — no Docker required to get started.

---

## Data Layout

All user data is stored under `~/.hivecore/`:

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

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| LLM interface | LiteLLM |
| Agent loop | ReAct (custom implementation) |
| Web backend | FastAPI + Uvicorn |
| Web frontend | React 18 + TypeScript + Vite + Tailwind CSS |
| Vector store | SQLite (default) / ChromaDB (optional) |
| Scheduler | APScheduler |
| Config | Pydantic Settings + TOML |
| CLI | Typer |
| Packaging | pyproject.toml (PEP 517) |

---

## Design Decisions

**Why single-agent?** Multi-agent frameworks introduce coordination overhead, debugging complexity, and fragility. A single well-equipped agent with good memory and tools outperforms a poorly-coordinated swarm for personal use cases.

**Why local-first memory?** Markdown files are durable, portable, and don't require a database migration when you update the software. You can `grep` your own memory, edit it by hand, and back it up with git.

**Why LiteLLM?** It provides a single unified interface for 100+ LLM providers. You can switch from GPT-4o to Claude to a local Ollama model by changing one line in `config.toml`.

**Why subprocess sandboxing over Docker?** Docker adds a significant installation burden for a personal tool. Subprocess isolation is sufficient for the common case and available everywhere Python runs. Docker support is planned for high-risk skill execution (see `FUTURE_ROADMAP.md`).

---

## Roadmap

See [FUTURE_ROADMAP.md](../FUTURE_ROADMAP.md) for planned features including Docker sandboxing, multi-agent support, MCP server integration, skill marketplace, and conversation branching.
