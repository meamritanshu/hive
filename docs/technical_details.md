# HiveCore — Technical Reference

## Package Structure

```
hivecore/
├── __init__.py              # __version__, __app_name__
├── __main__.py              # python -m hivecore entry point
├── cli/                     # Typer CLI
├── config/                  # Settings + defaults
├── core/                    # Agent, messages, LLM, tools, prompts
├── memory/                  # All memory subsystems
├── skills/                  # Skill system
├── runtime/                 # Executor, sandbox, lifecycle
├── automation/              # Scheduler, heartbeat
├── channels/                # Discord, Telegram, base/router
├── web/                     # FastAPI app + built frontend static files
└── utils/                   # Logging, EventBus
```

---

## CLI

Entry point: `hivecore` (or `python -m hivecore`)

### Commands

| Command | Description |
|---|---|
| `hivecore start` | Start the full workstation (web server + scheduler + channels) |
| `hivecore chat` | Launch an interactive CLI chat session |
| `hivecore config` | View or edit configuration settings |
| `hivecore skill` | List, install, or inspect skills |
| `hivecore schedule` | List, add, or remove scheduled jobs |
| `hivecore status` | Print current workstation status |

**Source:** `hivecore/cli/main.py` — Typer app with subcommands delegating to:
- `hivecore/cli/interactive.py` — interactive chat REPL
- `hivecore/cli/commands/config_cmd.py`
- `hivecore/cli/commands/skill_cmd.py`
- `hivecore/cli/commands/schedule_cmd.py`
- `hivecore/cli/commands/status_cmd.py`

---

## Configuration

**File:** `~/.hivecore/config.toml`  
**Class:** `HiveSettings` in `hivecore/config/settings.py`

`HiveSettings` is a Pydantic `BaseSettings` model. All fields can be set via `config.toml` or environment variables (prefixed `HIVECORE_`).

### Top-level fields

| Field | Type | Default | Description |
|---|---|---|---|
| `data_dir` | `Path` | `~/.hivecore` | Root directory for all user data |
| `log_level` | `str` | `"INFO"` | Logging verbosity |
| `debug` | `bool` | `False` | Enable debug mode |

### Sub-models

#### `LLMSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `provider` | `str` | `"litellm"` | Provider name: `litellm`, `openai`, `anthropic`, `google`, `azure`, `ollama` |
| `model` | `str` | `"gpt-4o"` | Model identifier (LiteLLM format) |
| `api_key` | `str \| None` | `None` | API key (or set via env var) |
| `api_base` | `str \| None` | `None` | Custom base URL (e.g. for Ollama: `http://localhost:11434`) |
| `temperature` | `float` | `0.7` | Sampling temperature |
| `max_tokens` | `int` | `4096` | Max tokens per response |
| `timeout` | `int` | `60` | Request timeout in seconds |

#### `MemorySettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `vector_store` | `str` | `"sqlite"` | Vector backend: `sqlite` or `chromadb` |
| `short_term_limit` | `int` | `50` | Max messages in short-term window |
| `embedding_provider` | `str` | `"api"` | Embedding source: `api`, `local`, `ollama` |
| `embedding_model` | `str` | `"text-embedding-ada-002"` | Embedding model name |
| `hybrid_vector_weight` | `float` | `0.7` | Vector score weight in hybrid retrieval (BM25 gets `1 - this`) |
| `top_k` | `int` | `5` | Number of results to retrieve |

#### `SkillsSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `skills_dir` | `Path` | `~/.hivecore/skills` | Directory for user-installed skills |
| `hot_reload` | `bool` | `True` | Watch for skill file changes and reload automatically |

#### `WebSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `host` | `str` | `"127.0.0.1"` | Bind address for the web server |
| `port` | `int` | `8088` | Port for the web server |
| `cors_origins` | `list[str]` | `["*"]` | Allowed CORS origins |

#### `ChannelsSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `discord_token` | `str \| None` | `None` | Discord bot token |
| `telegram_token` | `str \| None` | `None` | Telegram bot token |

#### `SchedulerSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `timezone` | `str` | `"UTC"` | Timezone for cron jobs |
| `heartbeat_interval` | `int` | `300` | Heartbeat interval in seconds |

#### `AgentSettings`
| Field | Type | Default | Description |
|---|---|---|---|
| `persona` | `str` | `"default"` | Active persona name |
| `max_iterations` | `int` | `10` | Max ReAct loop iterations per request |
| `system_prompt_extra` | `str` | `""` | Text appended to the system prompt |

**Defaults source:** `hivecore/config/defaults.py` — defines `PERSONA_PROMPTS`, `REACT_SYSTEM_TEMPLATE`, `MEMORY_FILE_HEADER`.

---

## Core — Agent

**File:** `hivecore/core/agent.py`  
**Class:** `Agent`

The main reasoning engine. Runs a ReAct loop: at each iteration the LLM produces either a tool call or a final answer.

### Constructor

```python
Agent(
    settings: HiveSettings,
    llm_provider: LLMProvider,
    tool_registry: ToolRegistry,
    memory_manager: MemoryManager,
)
```

### Key methods

| Method | Description |
|---|---|
| `async run(message: str, conversation: Conversation) -> str` | Run one user turn through the ReAct loop |
| `async stream(message: str, conversation: Conversation) -> AsyncIterator[str]` | Streaming version — yields text chunks |

### Message schema (`hivecore/core/messages.py`)

| Class | Description |
|---|---|
| `Role` | Enum: `USER`, `ASSISTANT`, `SYSTEM`, `TOOL` |
| `Message` | `role`, `content`, `tool_calls`, `tool_results`, `timestamp` |
| `Conversation` | List of `Message` objects with helper methods |
| `ToolCall` | `id`, `name`, `arguments` (dict) |
| `ToolResult` | `tool_call_id`, `name`, `result`, `error` |

---

## Core — LLM Providers

**Directory:** `hivecore/core/llm/`

### `LLMProvider` (abstract base — `base.py`)

| Method | Description |
|---|---|
| `async complete(messages, tools, **kwargs) -> Message` | Non-streaming completion |
| `async stream(messages, tools, **kwargs) -> AsyncIterator[str]` | Streaming completion |

### `LiteLLMProvider` (`litellm_provider.py`)

Default provider. Wraps `litellm.acompletion`. Handles tool call parsing and streaming delta accumulation.

### `OllamaProvider` (`litellm_provider.py`)

Subclass of `LiteLLMProvider`. Pre-configures `api_base` for Ollama and normalizes model name formatting.

### Provider Registry (`registry.py`)

```python
get_provider(settings: LLMSettings) -> LLMProvider
```

Registered providers: `litellm`, `openai`, `anthropic`, `google`, `azure`, `ollama`.

---

## Core — Tools

**Directory:** `hivecore/core/tools/`

### `BaseTool` (`base.py`)

Abstract base. Subclass and implement `async execute(**kwargs) -> str`.

```python
class BaseTool:
    name: str
    description: str
    parameters: list[ToolParameter]
    async def execute(self, **kwargs) -> str: ...
```

### `FunctionTool` (`base.py`)

Wraps a plain Python async function as a tool. Used internally by the `@tool` decorator.

### `@tool` decorator (`base.py`)

```python
@tool(name="my_tool", description="Does something useful")
async def my_tool(param: str) -> str:
    return f"result: {param}"
```

Parameter types are inferred from type annotations. Docstring is used as description if not provided.

### `ToolDefinition` / `ToolParameter` (`base.py`)

JSON-Schema-compatible parameter definitions passed to the LLM.

### `ToolRegistry` (`registry.py`)

```python
registry = ToolRegistry()
registry.register(tool)          # register a BaseTool instance
registry.get(name) -> BaseTool
registry.list() -> list[BaseTool]
registry.to_definitions() -> list[ToolDefinition]  # for LLM function calling
```

### Built-in Tools (`builtin/tools.py`)

| Tool name | Description |
|---|---|
| `read_file` | Read a file from disk |
| `write_file` | Write content to a file |
| `list_directory` | List files in a directory |
| `run_shell` | Execute a shell command |
| `web_search` | Search the web (requires API key config) |
| `get_current_time` | Return the current date and time |
| `calculate` | Evaluate a math expression |

---

## Memory System

**Directory:** `hivecore/memory/`

### `MemoryManager` (`manager.py`)

Coordinates all memory layers. The agent interacts with this class exclusively.

```python
class MemoryManager:
    async def add(entry: MemoryEntry) -> None
    async def search(query: str, top_k: int = 5) -> list[MemorySearchResult]
    async def get_context(query: str) -> str        # formatted string for prompt injection
    async def compact() -> None                      # trigger compaction
    async def stats() -> dict                        # memory statistics
```

### `MemoryEntry` / `MemoryType` (`types.py`)

```python
class MemoryType(Enum):
    PERSONAL = "personal"
    TASK = "task"
    TOOL = "tool"
    EPISODIC = "episodic"

class MemoryEntry:
    id: str
    content: str
    memory_type: MemoryType
    timestamp: datetime
    metadata: dict
```

### `ShortTermMemory` (`short_term.py`)

In-process deque capped at `settings.memory.short_term_limit` (default 50) messages.

### `FileMemory` (`long_term/file_memory.py`)

Writes and reads Markdown files under `~/.hivecore/memory/`. Files are organized by `MemoryType` and date. Human-readable and directly editable.

### `VectorMemory` (`long_term/vector_memory.py`)

Manages the vector store. Embeds new entries via `EmbeddingGenerator` and stores them. Supports `search(query, top_k)`.

### `MemoryCompactor` (`long_term/compactor.py`)

Summarizes old episodic memories using the LLM to reduce context window usage. Triggered by the heartbeat or manually.

### `HybridRetriever` (`retrieval/hybrid.py`)

Combines BM25 (keyword) and vector (semantic) search results using Reciprocal Rank Fusion (RRF).

- BM25 weight: `1 - hybrid_vector_weight` (default `0.3`)
- Vector weight: `hybrid_vector_weight` (default `0.7`)

```python
class HybridRetriever:
    async def search(query: str, top_k: int) -> list[MemorySearchResult]

class BM25Index:
    def index(documents: list[str]) -> None
    def search(query: str, top_k: int) -> list[tuple[int, float]]
```

### Vector Stores (`stores/sqlite.py`)

**`SQLiteVectorStore`** — Default. Stores embeddings in a SQLite table at `~/.hivecore/vectors.db`. No extra dependencies.

**`ChromaDBStore`** — Optional. Requires `pip install hivecore[chromadb]`. Persistent ChromaDB collection.

Both implement the same interface:
```python
async def add(id, embedding, metadata) -> None
async def search(query_embedding, top_k) -> list[dict]
async def delete(id) -> None
async def count() -> int
```

### `EmbeddingGenerator` (`index/embeddings.py`)

| Provider | Config value | Notes |
|---|---|---|
| API (OpenAI-compatible) | `"api"` | Uses `settings.llm.api_key` |
| Local (sentence-transformers) | `"local"` | Requires `pip install hivecore[embeddings-local]` |
| Ollama | `"ollama"` | Requires running Ollama instance |

```python
class EmbeddingGenerator:
    async def embed(text: str) -> list[float]
    async def embed_batch(texts: list[str]) -> list[list[float]]
```

---

## Skill System

**Directory:** `hivecore/skills/`

### `Skill` base class (`base.py`)

```python
class Skill:
    manifest: SkillManifest

    async def execute(self, **kwargs) -> str: ...
```

### `@skill` decorator (`base.py`)

```python
@skill(
    name="my_skill",
    description="Does something",
    parameters=[{"name": "topic", "type": "string", "required": True}],
    schedule="0 9 * * *",   # optional cron expression
)
async def my_skill(topic: str) -> str:
    return f"Result for {topic}"
```

### `SkillManifest` (`base.py`)

```python
class SkillManifest:
    name: str
    description: str
    version: str
    author: str
    parameters: list[dict]
    schedule: str | None     # cron expression
    tags: list[str]
```

### `SkillLoader` (`loader.py`)

Auto-discovers `.py` files in `~/.hivecore/skills/`. Supports hot-reload via file system watching. 

```python
class SkillLoader:
    def load_from_directory(path: Path) -> list[Skill]
    def reload(skill_name: str) -> Skill
    def watch(callback: Callable) -> None
```

### `SkillRegistry` (`registry.py`)

```python
class SkillRegistry:
    def register(skill: Skill) -> None
    def get(name: str) -> Skill
    def list() -> list[Skill]
    def get_scheduled() -> list[Skill]   # skills with a cron expression
```

### Built-in Skills

**`news_digest`** (`builtin/news_digest.py`) — Fetches and summarizes news headlines for a given topic. Parameters: `topic` (string, required), `count` (int, default 5).

---

## Runtime

**Directory:** `hivecore/runtime/`

### `start_workstation()` (`lifecycle.py`)

Top-level orchestration function. Called by `hivecore start`. Initializes all subsystems in order:
1. Load settings
2. Set up logging
3. Initialize `MemoryManager`
4. Initialize `ToolRegistry` with built-in tools
5. Initialize `SkillRegistry` + `SkillLoader`
6. Register skill-derived cron jobs with `Scheduler`
7. Start `Heartbeat`
8. Connect enabled channel adapters
9. Start FastAPI web server (Uvicorn)

### `Executor` (`executor.py`)

Runs tool and skill calls, capturing execution metrics.

```python
class Executor:
    async def run_tool(tool: BaseTool, **kwargs) -> ToolResult
    async def run_skill(skill: Skill, **kwargs) -> str
    def get_metrics() -> dict    # latency, success rate, call counts
```

### `SubprocessSandbox` (`sandbox/subprocess.py`)

Runs skill code in a subprocess to isolate it from the main process. Enforces a configurable timeout.

```python
class SubprocessSandbox:
    async def execute(code: str, timeout: int = 30) -> str
```

---

## Automation

**Directory:** `hivecore/automation/`

### `Scheduler` (`scheduler.py`)

Wraps APScheduler's `AsyncScheduler`. Persists jobs across restarts.

```python
class Scheduler:
    async def start() -> None
    async def stop() -> None
    def add_job(job: ScheduledJob) -> str          # returns job id
    def remove_job(job_id: str) -> None
    def list_jobs() -> list[ScheduledJob]
    def get_job(job_id: str) -> ScheduledJob | None
```

### `ScheduledJob` (`scheduler.py`)

```python
class ScheduledJob:
    id: str
    name: str
    cron: str               # standard cron expression
    skill_name: str | None  # run a skill
    prompt: str | None      # or run an agent prompt
    enabled: bool
    last_run: datetime | None
    next_run: datetime | None
```

### `Heartbeat` (`heartbeat.py`)

Runs every `settings.scheduler.heartbeat_interval` seconds (default 300s). Default tasks:
- Trigger `MemoryCompactor` if episodic memory exceeds threshold
- Emit `heartbeat` event on `EventBus`

```python
class Heartbeat:
    async def start() -> None
    async def stop() -> None
```

---

## Channels

**Directory:** `hivecore/channels/`

### `BaseChannel` (`base.py`)

Abstract interface for all channel adapters.

```python
class BaseChannel:
    name: str
    async def start() -> None
    async def stop() -> None
    async def send(message: str, recipient_id: str) -> None
    # Implementations call agent.run() on incoming messages
```

### `ChannelRouter` (`router.py`)

Manages all active channels. Routes inbound messages to the agent and outbound responses back to the originating channel.

```python
class ChannelRouter:
    def register(channel: BaseChannel) -> None
    async def start_all() -> None
    async def stop_all() -> None
```

### `DiscordChannel` (`discord_bot.py`)

Implements `BaseChannel` using `discord.py`. Responds to mentions and DMs. Requires `pip install hivecore[discord]` and a `discord_token` in config.

### `TelegramChannel` (`discord_bot.py`)

Implements `BaseChannel` using `python-telegram-bot`. Responds to `/chat` commands and direct messages. Requires `pip install hivecore[telegram]` and a `telegram_token` in config.

---

## Web API

**File:** `hivecore/web/api/app.py`  
**Framework:** FastAPI + Uvicorn  
Default URL: `http://127.0.0.1:8088`

The same process serves both the REST/WebSocket API and the React frontend static files (SPA catch-all on `/`).

### REST Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/status` | Workstation status: uptime, agent state, memory stats, active channels |
| `POST` | `/api/chat` | Single-turn chat. Body: `{"message": str, "conversation_id": str \| null}`. Returns `{"response": str}` |
| `GET` | `/api/memory/stats` | Memory statistics: entry counts by type, vector store size |
| `GET` | `/api/memory/search` | Search memory. Query params: `q` (string), `top_k` (int, default 5). Returns `list[MemorySearchResult]` |
| `GET` | `/api/skills` | List all registered skills and their manifests |
| `GET` | `/api/config` | Return current configuration as JSON (sensitive fields redacted) |
| `GET` | `/api/scheduler/jobs` | List all scheduled jobs |

### WebSocket Endpoint

**`WS /ws/chat`** — Streaming chat.

Send:
```json
{"message": "hello", "conversation_id": null}
```

Receive (one or more chunk messages, then done):
```json
{"type": "chunk", "content": "Hello"}
{"type": "chunk", "content": "! How can"}
{"type": "done"}
```

---

## Web Frontend

**Directory:** `frontend/`  
**Build output:** `hivecore/web/static/` (served by FastAPI)  
**Stack:** React 18, TypeScript (strict), Vite, Tailwind CSS, React Router v6

### Pages

| Route | Component | Description |
|---|---|---|
| `/` | `DashboardPage` | System status, memory stats, skills overview |
| `/chat` | `ChatPage` | WebSocket streaming chat interface |
| `/memory` | `MemoryPage` | Memory search + entry stats |
| `/skills` | `SkillsPage` | Skills list with expandable parameter details |
| `/config` | `ConfigPage` | Config viewer (nested sections) |
| `/scheduler` | `SchedulerPage` | Scheduled jobs list |

### API Client (`frontend/src/lib/api.ts`)

Typed fetch wrapper for all REST endpoints and a WebSocket client for `/ws/chat`.

### Theme

Custom Tailwind scales: `hive` (amber) for accent colors, `surface` (dark grays) for backgrounds. Dark mode only.

### Build

```bash
cd frontend
npm install
npm run build    # outputs to hivecore/web/static/
```

---

## Utilities

### `setup_logging()` (`utils/logging.py`)

Configures the Python `logging` module. Respects `settings.log_level`. Formats output for CLI readability.

### `EventBus` (`utils/events.py`)

Global pub/sub event system. Singleton accessible via `from hivecore.utils.events import event_bus`.

```python
class EventBus:
    def subscribe(event: str, handler: Callable) -> None
    def unsubscribe(event: str, handler: Callable) -> None
    async def emit(event: str, **data) -> None
```

Standard events emitted by the framework:

| Event | Emitted by | Payload |
|---|---|---|
| `heartbeat` | `Heartbeat` | `timestamp` |
| `memory.added` | `MemoryManager` | `entry: MemoryEntry` |
| `tool.executed` | `Executor` | `name`, `latency_ms`, `success` |
| `skill.executed` | `Executor` | `name`, `latency_ms`, `success` |
| `agent.turn.start` | `Agent` | `message` |
| `agent.turn.end` | `Agent` | `response` |

---

## Optional Dependencies

Install extras as needed:

| Extra | Command | Provides |
|---|---|---|
| ChromaDB vector store | `pip install hivecore[chromadb]` | `ChromaDBStore` |
| Discord channel | `pip install hivecore[discord]` | `DiscordChannel` |
| Telegram channel | `pip install hivecore[telegram]` | `TelegramChannel` |
| Local embeddings | `pip install hivecore[embeddings-local]` | `sentence-transformers` |
| All extras | `pip install hivecore[all]` | Everything above |
| Development tools | `pip install hivecore[dev]` | pytest, ruff, mypy, etc. |
