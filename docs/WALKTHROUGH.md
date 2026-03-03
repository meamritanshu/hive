# HiveCore — Walkthrough

> A guided tour of the codebase: what HiveCore is, how it works, and every architectural change made. Last updated: 2026-03-04. All 5 fixes from PROPOSED_FIXES.md are complete. Coverage target (80%) met. See `docs/STATUS.md` for the live task tracker.

---

## Table of Contents

1. [What is HiveCore?](#1-what-is-hivecore)
2. [Repository Layout](#2-repository-layout)
3. [Core Concepts](#3-core-concepts)
4. [Fix 1 — Skill Hardening](#4-fix-1--skill-hardening)
5. [Fix 2 — Shadow Indexing + Tiered Compaction](#5-fix-2--shadow-indexing--tiered-compaction)
6. [Fix 3a — Reflection & Self-Correction](#6-fix-3a--reflection--self-correction)
7. [Fix 3b — Session-Keyed ShortTermMemory](#7-fix-3b--session-keyed-shorttermmemory)
8. [Fix 4 — Git-Integrated Memory](#8-fix-4--git-integrated-memory)
9. [Fix 5 — Execution Provider Pattern](#9-fix-5--execution-provider-pattern)
10. [Test Suite](#10-test-suite)
11. [What's Next](#11-whats-next)
12. [Session Close — State Snapshot](#12-session-close--state-snapshot)

---

## 1. What is HiveCore?

HiveCore is a **personal AI agent workstation** that runs locally on your machine. You interact with it via a CLI (`hivecore`) or a web console. Under the hood it:

- Talks to an LLM (via LiteLLM, so any OpenAI-compatible model works).
- Uses a **ReAct loop** (Reasoning + Acting) to decide when to call tools, when to read/write memory, and when to produce a final answer.
- Stores conversation history in **short-term memory** (in-process), episodic logs and knowledge in **long-term memory** (Markdown files + SQLite vector store), and can optionally sync all of that to Git.
- Executes **Skills** — user-defined Python scripts that act as callable tools — in sandboxed subprocesses (or Docker containers).
- Runs background automation via scheduled tasks (heartbeat, compaction).

---

## 2. Repository Layout

```
hivecore/
├── cli/                    # Click CLI entrypoints
├── channels/               # Discord bot, future Slack etc.
├── config/
│   └── settings.py         # Pydantic-based config (reads ~/.hivecore/config.toml)
├── core/
│   ├── agent.py            # The Agent class — ReAct loop, tool dispatch, memory hooks
│   ├── messages.py         # Message dataclasses (UserMessage, AssistantMessage, ToolResult…)
│   ├── llm/
│   │   ├── base.py         # LLMProvider ABC
│   │   ├── litellm_provider.py  # Production LiteLLM implementation
│   │   └── registry.py     # Provider registry
│   ├── prompt/
│   │   └── builder.py      # System-prompt assembly
│   └── tools/
│       ├── base.py         # FunctionTool, ToolResult dataclasses
│       ├── registry.py     # ToolRegistry
│       └── builtin/
│           └── tools.py    # Built-in tools: read_file, write_file, run_shell, web_search…
├── memory/
│   ├── manager.py          # MemoryManager — central coordinator
│   ├── short_term.py       # ShortTermMemory — in-process sliding window
│   ├── types.py            # MemoryEntry, MemoryType enums
│   ├── git_sync.py         # MemoryGitSync — auto-commit memory dir to Git  [NEW]
│   ├── index/
│   │   └── embeddings.py   # Embedding generation + caching
│   ├── long_term/
│   │   ├── compactor.py    # MemoryCompactor (legacy) + TieredMemoryCompactor  [REWRITTEN]
│   │   ├── file_memory.py  # Markdown file read/write
│   │   └── vector_memory.py # VectorMemory — stores embeddings
│   ├── retrieval/
│   │   ├── hybrid.py       # HybridRetriever — BM25 + vector fusion
│   │   └── shadow_index.py # ShadowIndex — DuckDB FTS / LIKE fallback  [NEW]
│   └── stores/
│       └── sqlite.py       # SQLiteVectorStore + ChromaDBStore
├── runtime/
│   ├── executor.py         # HiveRuntime — orchestrates execution
│   ├── lifecycle.py        # Start/stop lifecycle manager
│   ├── config.py           # Runtime config loader
│   └── sandbox/
│       ├── base.py         # ExecutionProvider ABC  [NEW]
│       ├── subprocess.py   # SubprocessSandbox / SubprocessProvider  [MODIFIED]
│       ├── docker_provider.py  # DockerProvider  [NEW]
│       └── factory.py      # get_execution_provider() factory  [NEW]
├── skills/
│   ├── base.py             # SkillManifest, SkillContext, parse_requirements_header()  [REWRITTEN]
│   ├── loader.py           # SkillLoader — load, permission-check, install deps  [REWRITTEN]
│   ├── registry.py         # SkillRegistry
│   └── builtin/
│       └── news_digest.py  # Example built-in skill
├── automation/
│   ├── scheduler.py        # APScheduler wrapper
│   └── heartbeat.py        # Background compaction trigger
├── web/
│   └── api/
│       └── app.py          # FastAPI web console backend
└── utils/
    ├── logging.py          # Structlog thin wrapper
    └── events.py           # Simple event bus

tests/
├── conftest.py             # Shared pytest fixtures
├── unit/                   # Fast, isolated unit tests
└── integration/            # Tests that spin up real MemoryManager / compactor
```

---

## 3. Core Concepts

### The ReAct Loop (`core/agent.py`)

```
User message
    │
    ▼
[Prompt builder: system prompt + conversation history + memory context]
    │
    ▼
LLM call  ──► plain text?  ──► return to user
    │
    ▼ tool call
[ToolRegistry.dispatch(name, args)]
    │
    ▼
ToolResult  ──► append to history ──► loop back to LLM
```

The loop runs until the LLM returns plain text or `max_iterations` is hit. After the loop, a final summarisation call is made.

### Memory layers

| Layer | Class | Storage | Purpose |
|-------|-------|---------|---------|
| Short-term | `ShortTermMemory` | In-process list | Sliding window of current conversation |
| Long-term episodic | `FileMemory` | `~/.hivecore/memory/episodic/` Markdown | Full conversation logs |
| Long-term knowledge | `FileMemory` | `~/.hivecore/memory/knowledge/` Markdown | Curated facts, summaries |
| Vector store | `SQLiteVectorStore` | `~/.hivecore/memory/vectors.db` | Embedding-based similarity search |
| Shadow index | `ShadowIndex` | DuckDB in-memory or `vectors.duckdb` | Fast full-text search over memory entries |

### Skills vs. Built-in Tools

- **Built-in tools** (`core/tools/builtin/tools.py`): always available, implemented as Python functions decorated with `@tool`.
- **Skills** (`skills/`): user-defined Python scripts discovered from `~/.hivecore/skills/`. They are loaded, permission-checked, dependency-installed, and registered as tools at startup.

---

## 4. Fix 1 — Skill Hardening

**Problem**: Skills ran with full access to the host — they could read `config.toml` (containing API keys), write anywhere, and make arbitrary network calls.

### Changes

#### `hivecore/skills/base.py`

- **`SkillContext`** — a restricted context object passed to skills instead of the full config. Contains only the specific keys the skill declared it needs.
- **`SkillManifest.__post_init__`** — validates that `permissions` contains only known permission names; raises `ValueError` on unknown entries.
- **`parse_requirements_header(source: str) -> list[str]`** — scans the first lines of a skill script for `# Requirements: pkg1, pkg2` and returns the list.
- **`ensure_requirements(packages: list[str])`** — calls `pip install` for any listed packages not already importable.

#### `hivecore/skills/loader.py`

- **Permission enforcement**: before executing a skill, `SkillLoader` checks the skill's declared `permissions` against `SkillsSettings.default_permissions`. Skills requesting undeclared permissions are rejected.
- **Per-skill allow-list files**: a `skill_name.toml` file next to the skill script can grant additional permissions for that skill only.
- **Requirements installation**: `loader.load_skill()` calls `parse_requirements_header()` + `ensure_requirements()` before registering the skill.

#### `hivecore/config/settings.py`

- `SkillsSettings.default_permissions: list[str]` — global whitelist of allowed permission names.
- `SkillsSettings.sandbox_type: str` — `"subprocess"` or `"docker"`, wires into the executor factory.
- `_clean_for_toml()` — recursive helper that strips `None` values before serialising to TOML (TOML has no null type, replacing the old `_settings_to_dict`).

---

## 5. Fix 2 — Shadow Indexing + Tiered Compaction

**Problem**: `HybridRetriever` read physical Markdown files on every query — slow at scale. The single `MemoryCompactor` produced a flat summary with no granularity.

### Shadow Index

#### `hivecore/memory/retrieval/shadow_index.py` (NEW)

```python
class ShadowIndex:
    async def upsert(self, entry_id: str, text: str, metadata: dict) -> None: ...
    async def delete(self, entry_id: str) -> None: ...
    async def search_text(self, query: str, limit: int = 10) -> list[dict]: ...
    async def rebuild(self, entries: list[MemoryEntry]) -> None: ...
    async def count(self) -> int: ...
```

- Uses **DuckDB FTS** (`PRAGMA fts5`) when `duckdb` is installed.
- Falls back to **`LIKE` search** (SQLite-based) when DuckDB is not available.
- `MemoryManager` calls `upsert()` on every `store()` / `store_conversation()` and passes `shadow_index` results into `HybridRetriever`.

### Tiered Compaction

#### `hivecore/memory/long_term/compactor.py` (REWRITTEN)

```
Raw episodic logs
    │
    ▼  Tier 1 (< 7 days old) — kept verbatim
    │
    ▼  Tier 2 (7–30 days old) — LLM summarises each week into a single entry
    │
    ▼  Tier 3 (> 30 days old) — LLM extracts named entities (People, Places, Facts)
                                 and writes them to knowledge/personal.md
```

- **`TieredMemoryCompactor`** — new class implementing the three-tier pipeline.
- **`MemoryCompactor`** (legacy) — preserved as-is for backward compatibility.
- After a non-empty compaction cycle, auto-commits via `memory_manager._git_sync` (if available).

---

## 6. Fix 3a — Reflection & Self-Correction

**Problem**: If a tool consistently returns errors (bad arguments, wrong tool chosen, network down), the ReAct loop would spin up to `max_iterations` making the same mistake repeatedly.

### Changes

#### `hivecore/core/agent.py`

```python
_REFLECTION_FAILURE_THRESHOLD = 3
```

Inside `_react_loop()`:

```python
consecutive_failures = 0

# after each tool call:
if result.error:
    consecutive_failures += 1
    if consecutive_failures >= _REFLECTION_FAILURE_THRESHOLD:
        # inject a [Self-Reflection] user message into history
        history.append(UserMessage(
            content="[Self-Reflection] You have failed 3 times in a row. "
                    "Why is this failing? Consider: wrong tool, bad arguments, "
                    "or an incorrect assumption. Try a different approach."
        ))
        consecutive_failures = 0
else:
    consecutive_failures = 0
```

The injected message is a standard `UserMessage` so the LLM sees it in context on the next iteration and can adjust its strategy.

---

## 7. Fix 3b — Session-Keyed ShortTermMemory

**Problem**: `MemoryManager` held a single global `ShortTermMemory`. Messages from a Discord channel and the CLI would intermingle, confusing the agent.

### Changes

#### `hivecore/memory/manager.py`

Before:
```python
self._short_term = ShortTermMemory(max_tokens=settings.max_short_term_tokens)
```

After:
```python
self._sessions: dict[str, ShortTermMemory] = {}

def get_session(self, session_id: str = "default") -> ShortTermMemory:
    if session_id not in self._sessions:
        self._sessions[session_id] = ShortTermMemory(
            max_tokens=self._settings.max_short_term_tokens
        )
    return self._sessions[session_id]

@property
def _short_term(self) -> ShortTermMemory:
    """Backward-compatible alias for the default session."""
    return self.get_session("default")
```

Each channel now calls `manager.get_session("discord_channel_123")` and gets its own isolated sliding window. The vector store and long-term memory remain shared.

---

## 8. Fix 4 — Git-Integrated Memory

**Problem**: Memory files in `~/.hivecore/` had no version history. A bad compaction run could destroy information irreversibly.

### Changes

#### `hivecore/memory/git_sync.py` (NEW)

```python
class MemoryGitSync:
    def __init__(self, memory_dir: Path): ...
    async def initialize(self) -> None:
        # runs `git init` if not already a repo; creates .gitignore
    async def commit(self, message: str) -> bool:
        # stages all changes with `git add -A` and commits
        # returns True if a commit was created, False if nothing changed
    async def get_log(self, limit: int = 10) -> list[dict]:
        # returns recent commits as list of {hash, message, timestamp}
```

#### `hivecore/memory/manager.py`

- `initialize()` creates a `MemoryGitSync` instance and calls `git_sync.initialize()`.
- `compact_if_needed()` calls `git_sync.commit("compaction: <timestamp>")` after a non-empty cycle.

#### `hivecore/memory/long_term/compactor.py`

- `TieredMemoryCompactor.run()` checks `memory_manager._git_sync` and auto-commits with a descriptive message.

---

## 9. Fix 5 — Execution Provider Pattern

**Problem**: Code execution was hard-coded to subprocess. Adding Docker required invasive changes. Users had no way to switch.

### Changes

#### `hivecore/runtime/sandbox/base.py` (NEW)

```python
class ExecutionProvider(ABC):
    @abstractmethod
    async def execute_code(
        self,
        code: str,
        language: str = "python",
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
    ) -> dict:  # {"stdout": str, "stderr": str, "exit_code": int, "success": bool}
        ...

    @abstractmethod
    async def is_available(self) -> bool: ...
```

#### `hivecore/runtime/sandbox/subprocess.py`

- `SubprocessSandbox` now inherits from `ExecutionProvider`.
- Added a general `except Exception` handler so `OSError` from `create_subprocess_exec` returns a failure dict instead of propagating.
- `SubprocessProvider = SubprocessSandbox` alias added at module bottom.

#### `hivecore/runtime/sandbox/docker_provider.py` (NEW)

- `DockerProvider` implements `ExecutionProvider`.
- Runs code in a temporary Docker container (`python:3.11-slim` default image).
- `is_available()` pings the Docker daemon; returns `False` gracefully if Docker is not running.

#### `hivecore/runtime/sandbox/factory.py` (NEW)

```python
def get_execution_provider(
    sandbox_type: str = "subprocess",
    **kwargs,
) -> ExecutionProvider:
    if sandbox_type == "docker":
        return DockerProvider(**kwargs)
    return SubprocessProvider(**kwargs)
```

#### `hivecore/runtime/executor.py`

- `HiveRuntime.__init__` now accepts `sandbox_type: str` and `provider: ExecutionProvider | None`.
- If `provider` is given, it is used directly. Otherwise `get_execution_provider(sandbox_type)` is called.
- This means the config key `skills.sandbox_type = "docker"` is enough to switch the entire runtime to Docker.

---

## 10. Test Suite

### Philosophy

- **Unit tests** are fully isolated: LLM calls are mocked with `AsyncMock`, filesystem is `tmp_path`, no network.
- **Integration tests** spin up a real `MemoryManager` with a temporary directory, use actual SQLite and file I/O.
- Tests that need optional dependencies (`duckdb`, `chromadb`) skip gracefully with `pytest.importorskip`.

### Test Files

| File | What it covers |
|------|---------------|
| `tests/conftest.py` | Shared fixtures: `tmp_memory_dir`, `mock_llm`, `basic_agent` |
| `tests/unit/test_agent.py` | ReAct loop, tool calls, max iterations, self-reflection, `run_stream`, memory hooks, `register_tool`, `clear_conversation`, `memory_stats`, `shutdown`, `initialize` (~32 tests) |
| `tests/unit/test_builtin_tools.py` | `read_file`, `write_file`, `list_directory`, `run_shell`, `get_current_time`, `calculate`, `_human_size`, `_parse_ddg_lite`, `web_search`, `register_builtin_tools` (50 tests) |
| `tests/unit/test_shadow_index.py` | `ShadowIndex` init/lifecycle, `_check_duckdb`, `upsert`, `delete`, `_like_search`, `search_text` (FTS + LIKE fallback + both fail), `rebuild`, `count` (~35 tests) |
| `tests/unit/test_llm_registry.py` | `register_provider`, `get_provider` (known/unknown/case-insensitive), `list_providers`, `_ensure_default_providers` (~15 tests) |
| `tests/unit/test_embeddings.py` | `embed([])`, `_embed_api` (mocked litellm), `_embed_local` (mocked sentence_transformers), `_embed_ollama` (mocked httpx), `dimension` property (~16 tests) |
| `tests/unit/test_executor.py` | `Executor.__init__` variants, `execute` (unknown tool/success/failure/sandbox), `get_execution_log`, `get_stats` (~22 tests) |
| `tests/unit/test_git_sync.py` | `MemoryGitSync`: init, commit, no-op commit, log, missing git |
| `tests/unit/test_memory.py` | `ShortTermMemory`, session-keyed sessions, backward compat alias |
| `tests/unit/test_sandbox.py` | `ExecutionProvider` ABC, `SubprocessSandbox`, `DockerProvider`, factory |
| `tests/unit/test_skills_hardening.py` | `SkillManifest` validation, `SkillContext`, `parse_requirements_header`, permission enforcement |
| `tests/unit/test_tools.py` | `FunctionTool`, `ToolRegistry`, error re-raise behaviour |
| `tests/unit/test_messages.py` | Message dataclasses, serialisation |
| `tests/unit/test_settings.py` | Config load, save, `_clean_for_toml` |
| `tests/unit/test_vector_store.py` | `SQLiteVectorStore` CRUD, cosine similarity |
| `tests/unit/test_skills.py` | `SkillRegistry`, loader basics |
| `tests/integration/test_memory_manager.py` | Full `MemoryManager` lifecycle: init, store, retrieve, sessions, git sync |
| `tests/integration/test_tiered_compaction.py` | `TieredMemoryCompactor` Tier1/2/3 pipeline |

### Running Tests

```bash
# All tests
python -m pytest tests/

# With coverage report
python -m pytest tests/ --cov=hivecore --cov-report=term-missing

# Single file
python -m pytest tests/unit/test_agent.py -v
```

**Current result: 352 passed, 1 skipped, overall 80.84% coverage.**

### Known Gotchas

- **Windows file locking**: Always call `await mgr.close()` before `pytest.skip()` inside a `TemporaryDirectory` block — SQLite holds the file open.
- **`FunctionTool.execute()` re-raises**: Use `pytest.raises(SomeError)` not string checks on `ToolResult.error`.
- **`asyncio_mode = "auto"`**: The `PytestConfigWarning` from pytest 9.0.2 is benign.

---

## 11. What's Next

See `docs/STATUS.md` for the full task list. Phase 2 (coverage + CI) is complete.

### Optional Stretch Goals (not required — 80% target already met)

| Module | Coverage | Key gaps |
|--------|----------|---------|
| `skills/loader.py` | 45% | Dir-skill loading, reload, `unload_all` |
| `runtime/sandbox/docker_provider.py` | 52% | Docker sandbox (low priority, infra) |
| `memory/stores/sqlite.py` | 64% | `ChromaDBStore` — skip when `chromadb` not installed |
| `memory/long_term/compactor.py` | 67% | Legacy `MemoryCompactor` paths |
| `memory/long_term/vector_memory.py` | 68% | `VectorMemory` store/retrieve paths |
| `memory/manager.py` | 71% | Session-keyed memory, compaction paths |
| `memory/git_sync.py` | 73% | Git commit / push error paths |
| `core/tools/registry.py` | 78% | `list_by_category`, `unregister` |

### Phase 3 — Future Features

Move to Phase 3 features from `FUTURE_ROADMAP.md` (multi-agent, MCP, skill marketplace).

---

## 12. Session Close — State Snapshot

> Recorded: 2026-03-04 (end of session 2)

### What was accomplished

#### Session 1 — Architectural fixes
| Category | Detail |
|----------|--------|
| Fixes implemented | All 5 from `PROPOSED_FIXES.md` |
| New files created | `memory/git_sync.py`, `memory/retrieval/shadow_index.py`, `runtime/sandbox/base.py`, `runtime/sandbox/docker_provider.py`, `runtime/sandbox/factory.py` |
| Files rewritten | `skills/base.py`, `skills/loader.py`, `memory/long_term/compactor.py` |
| Files modified | `core/agent.py`, `memory/manager.py`, `runtime/executor.py`, `runtime/sandbox/subprocess.py`, `config/settings.py` |
| Test files created | `test_agent.py`, `test_git_sync.py`, `test_sandbox.py`, `test_skills_hardening.py`, `test_memory_manager.py`, `test_tiered_compaction.py` |
| Test count | 193 passed, 1 skipped |
| Overall coverage | 50% |

#### Session 2 — Coverage + CI
| Category | Detail |
|----------|--------|
| Coverage config | `[tool.coverage]` in `pyproject.toml` with `omit` list and `fail_under = 80` |
| New test files | `test_builtin_tools.py` (50), `test_shadow_index.py` (~35), `test_llm_registry.py` (~15), `test_embeddings.py` (~16), `test_executor.py` (~22) |
| Extended test files | `test_agent.py` (7 → ~32 tests) |
| CI workflow | `.github/workflows/ci.yml` — Python 3.11 + 3.12 matrix |
| Test count | 352 passed, 1 skipped |
| Overall coverage | **80.84%** ✅ (target: 80%) |

### Key modules improved
| Module | Before | After |
|--------|--------|-------|
| `core/tools/builtin/tools.py` | 23% | 92% |
| `memory/retrieval/shadow_index.py` | 32% | 92% |
| `core/llm/registry.py` | 34% | 100% |
| `memory/index/embeddings.py` | 40% | 100% |
| `runtime/executor.py` | 48% | 98% |
| `core/agent.py` | 73% | 97% |

### Where to resume

Phase 2 is complete. Options:
- **Stretch goals**: Fill remaining coverage gaps (see STATUS.md "Remaining Gaps" table) to push toward 90%+
- **Phase 3**: Begin feature work from `FUTURE_ROADMAP.md` (multi-agent, MCP, skill marketplace)

### Environment notes

- Python 3.13.7 on Windows (win32)
- `pip install -e ".[dev]"` installs all deps including `rank_bm25`, `aiosqlite`, `tomli-w`, `pytest-asyncio`, `pytest-cov`
- `duckdb` and `chromadb` are optional — tests skip gracefully without them
- Run tests: `python -m pytest tests/ --cov=hivecore --cov-report=term-missing`
