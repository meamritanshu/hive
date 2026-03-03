# HiveCore — Project Status

> Last updated: 2026-03-04 (session 4)
> Current test count: 352 passed, 1 skipped | Overall coverage: 80.80% (target: 80%)

---

## Legend

- ✅ Complete
- 🔄 In Progress
- ⬜ Not Started
- ❌ Blocked / Won't Do (this session)

---

## Session Summary

**Session 1** completed all 5 architectural fixes from `docs/PROPOSED_FIXES.md` and built a 193-test suite from scratch.

**Session 2** raised coverage from 50% to 80.84%, added 6 new test files (~159 new tests), and created the GitHub Actions CI workflow.

**Session 3** made the web console Config page fully interactive — users can now edit and save all HiveCore settings from the browser.

**Session 4** diagnosed and fixed a port conflict (`[WinError 10048]`) when starting the server. Confirmed that `WebSettings` already had `host`/`port` fields, `lifecycle.py` already accepted those parameters, and `hivecore start` already had `--host`/`--port` CLI flags — the architecture was complete. Killed the stale process on port 8088 so the server starts cleanly again.

| Milestone | Result |
|-----------|--------|
| PROPOSED_FIXES.md fixes implemented | 5 / 5 ✅ |
| Total tests | 352 passed, 1 skipped |
| Overall coverage | 80.80% ✅ |
| Coverage target (`fail_under`) | 80% — enforced in `pyproject.toml` |
| CI/CD pipeline | ✅ `.github/workflows/ci.yml` (Python 3.11 + 3.12 matrix) |
| Interactive config panel | ✅ `PATCH /api/config` + rewritten `ConfigPage.tsx` |
| Port configurable via settings + CLI | ✅ `WebSettings.host/port`, `--host`/`--port` flags |
| Next session start point | Optional stretch goals or Phase 4 features |

---

## Phase 1 — PROPOSED_FIXES.md (all 5 fixes)

### Fix 1 — Skill Hardening ✅

| Task | Status | File(s) |
|------|--------|---------|
| `SkillContext` restricted context object | ✅ | `hivecore/skills/base.py` |
| Permission validation at load time | ✅ | `hivecore/skills/base.py` |
| `parse_requirements_header()` — parse `# Requirements:` from script | ✅ | `hivecore/skills/base.py` |
| `ensure_requirements()` — auto-install per-skill deps | ✅ | `hivecore/skills/base.py` |
| `SkillManifest.__post_init__` validation | ✅ | `hivecore/skills/base.py` |
| Permission enforcement in loader | ✅ | `hivecore/skills/loader.py` |
| Requirements installation in loader | ✅ | `hivecore/skills/loader.py` |
| Per-skill allow-list files (`skill_name.toml`) | ✅ | `hivecore/skills/loader.py` |
| `SkillsSettings.default_permissions` + `sandbox_type` in config | ✅ | `hivecore/config/settings.py` |

### Fix 2 — Shadow Indexing + Tiered Compaction ✅

| Task | Status | File(s) |
|------|--------|---------|
| `ShadowIndex` — DuckDB FTS with LIKE fallback | ✅ | `hivecore/memory/retrieval/shadow_index.py` (NEW) |
| Wire shadow index into `MemoryManager` | ✅ | `hivecore/memory/manager.py` |
| `TieredMemoryCompactor` — Tier1 (raw 7d) → Tier2 (weekly summary) → Tier3 (entities) | ✅ | `hivecore/memory/long_term/compactor.py` |
| Legacy `MemoryCompactor` preserved for backward compat | ✅ | `hivecore/memory/long_term/compactor.py` |

### Fix 3a — Reflection / Self-Correction ✅

| Task | Status | File(s) |
|------|--------|---------|
| `_REFLECTION_FAILURE_THRESHOLD = 3` constant | ✅ | `hivecore/core/agent.py` |
| `consecutive_failures` counter in `_react_loop()` | ✅ | `hivecore/core/agent.py` |
| Inject `[Self-Reflection]` message after 3 consecutive `ToolResult.error`s | ✅ | `hivecore/core/agent.py` |

### Fix 3b — Session-Keyed ShortTermMemory ✅

| Task | Status | File(s) |
|------|--------|---------|
| Replace `self._short_term` with `self._sessions: dict[str, ShortTermMemory]` | ✅ | `hivecore/memory/manager.py` |
| `get_session(session_id)` public method | ✅ | `hivecore/memory/manager.py` |
| `_short_term` property as backward-compatible alias | ✅ | `hivecore/memory/manager.py` |

### Fix 4 — Git-Integrated Memory ✅

| Task | Status | File(s) |
|------|--------|---------|
| `MemoryGitSync` class — init repo, stage, commit | ✅ | `hivecore/memory/git_sync.py` (NEW) |
| Wire `_git_sync` into `MemoryManager.initialize()` | ✅ | `hivecore/memory/manager.py` |
| Auto-commit after `compact_if_needed()` | ✅ | `hivecore/memory/manager.py` |
| Auto-commit after non-empty compaction cycle | ✅ | `hivecore/memory/long_term/compactor.py` |

### Fix 5 — Execution Provider Pattern ✅

| Task | Status | File(s) |
|------|--------|---------|
| `ExecutionProvider` ABC | ✅ | `hivecore/runtime/sandbox/base.py` (NEW) |
| `SubprocessProvider` implements `ExecutionProvider` | ✅ | `hivecore/runtime/sandbox/subprocess.py` |
| `DockerProvider` — Docker-based execution | ✅ | `hivecore/runtime/sandbox/docker_provider.py` (NEW) |
| `get_execution_provider()` factory | ✅ | `hivecore/runtime/sandbox/factory.py` (NEW) |
| `HiveRuntime` / executor uses factory; accepts `sandbox_type` and `provider` | ✅ | `hivecore/runtime/executor.py` |

---

## Phase 2 — Test Suite

### Unit Tests ✅

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/unit/test_agent.py` | ~32 | ✅ (extended from 7 in session 2) |
| `tests/unit/test_builtin_tools.py` | 50 | ✅ (NEW in session 2) |
| `tests/unit/test_shadow_index.py` | ~35 | ✅ (NEW in session 2) |
| `tests/unit/test_llm_registry.py` | ~15 | ✅ (NEW in session 2) |
| `tests/unit/test_embeddings.py` | ~16 | ✅ (NEW in session 2) |
| `tests/unit/test_executor.py` | ~22 | ✅ (NEW in session 2) |
| `tests/unit/test_git_sync.py` | 10 | ✅ |
| `tests/unit/test_memory.py` | extended | ✅ |
| `tests/unit/test_sandbox.py` | 21 | ✅ |
| `tests/unit/test_skills_hardening.py` | 50 | ✅ |
| `tests/unit/test_tools.py` | updated | ✅ |
| `tests/unit/test_messages.py` | existing | ✅ |
| `tests/unit/test_settings.py` | existing | ✅ |
| `tests/unit/test_vector_store.py` | existing | ✅ |
| `tests/unit/test_skills.py` | existing | ✅ |

### Integration Tests ✅

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/integration/test_memory_manager.py` | 14 | ✅ |
| `tests/integration/test_tiered_compaction.py` | 9 | ✅ |

**Total: 352 passed, 1 skipped**

---

## Per-Module Coverage Snapshot

> Captured: 2026-03-04 (after session 2) | `python -m pytest tests/ --cov=hivecore --cov-report=term-missing`

| Module | Coverage | Omit from CI? | Notes |
|--------|----------|---------------|-------|
| `hivecore/__init__.py` | 100% | No | |
| `hivecore/__main__.py` | 0% | Yes | needs live service |
| `hivecore/automation/heartbeat.py` | 0% | Yes | needs live service |
| `hivecore/automation/scheduler.py` | 0% | Yes | needs live service |
| `hivecore/channels/base.py` | 0% | Yes | needs live service |
| `hivecore/channels/discord_bot.py` | 0% | Yes | needs live service |
| `hivecore/channels/router.py` | 0% | Yes | needs live service |
| `hivecore/config/settings.py` | 98% | No | |
| `hivecore/core/agent.py` | **97%** | No | ↑ from 73% |
| `hivecore/core/llm/base.py` | 95% | No | |
| `hivecore/core/llm/litellm_provider.py` | 0% | Yes | needs live service |
| `hivecore/core/llm/registry.py` | **100%** | No | ↑ from 34% |
| `hivecore/core/messages.py` | 97% | No | |
| `hivecore/core/prompt/builder.py` | 95% | No | |
| `hivecore/core/tools/base.py` | 96% | No | |
| `hivecore/core/tools/builtin/tools.py` | **92%** | No | ↑ from 23% |
| `hivecore/core/tools/registry.py` | 78% | No | |
| `hivecore/memory/git_sync.py` | 73% | No | |
| `hivecore/memory/index/embeddings.py` | **100%** | No | ↑ from 40% |
| `hivecore/memory/long_term/compactor.py` | 67% | No | |
| `hivecore/memory/long_term/file_memory.py` | 86% | No | |
| `hivecore/memory/long_term/vector_memory.py` | 68% | No | |
| `hivecore/memory/manager.py` | 71% | No | |
| `hivecore/memory/retrieval/hybrid.py` | 99% | No | |
| `hivecore/memory/retrieval/shadow_index.py` | **92%** | No | ↑ from 32% |
| `hivecore/memory/short_term.py` | 89% | No | |
| `hivecore/memory/stores/sqlite.py` | 64% | No | |
| `hivecore/memory/types.py` | 100% | No | |
| `hivecore/runtime/config.py` | 0% | Yes | needs live service |
| `hivecore/runtime/executor.py` | **98%** | No | ↑ from 48% |
| `hivecore/runtime/lifecycle.py` | 0% | Yes | needs live service |
| `hivecore/runtime/sandbox/base.py` | 100% | No | |
| `hivecore/runtime/sandbox/docker_provider.py` | 52% | No | |
| `hivecore/runtime/sandbox/factory.py` | 89% | No | |
| `hivecore/runtime/sandbox/subprocess.py` | 80% | No | |
| `hivecore/skills/base.py` | 94% | No | |
| `hivecore/skills/builtin/news_digest.py` | 0% | Yes | needs live service |
| `hivecore/skills/loader.py` | 45% | No | largest remaining gap |
| `hivecore/skills/registry.py` | 83% | No | |
| `hivecore/utils/events.py` | 0% | Yes | needs live service |
| `hivecore/utils/logging.py` | 0% | Yes | needs live service |
| `hivecore/web/api/app.py` | 0% | Yes | needs live service |

---

## Phase 2 — Coverage & CI

### Coverage Configuration ✅

| Task | Status | Notes |
|------|--------|-------|
| Measure baseline coverage | ✅ | Session 1: 50% — 3230 stmts, 1617 missed |
| Add `[tool.coverage]` to `pyproject.toml` | ✅ | Omits infra modules; `fail_under = 80` enforced |
| Reach 80%+ overall coverage | ✅ | 80.80% (352 passed, 1 skipped) |

### New Tests Written (session 2)

| Module | Before | After | Test File | Status |
|--------|--------|-------|-----------|--------|
| `core/tools/builtin/tools.py` | 23% | 92% | `tests/unit/test_builtin_tools.py` (50 tests) | ✅ |
| `memory/retrieval/shadow_index.py` | 32% | 92% | `tests/unit/test_shadow_index.py` (~35 tests) | ✅ |
| `core/llm/registry.py` | 34% | 100% | `tests/unit/test_llm_registry.py` (~15 tests) | ✅ |
| `memory/index/embeddings.py` | 40% | 100% | `tests/unit/test_embeddings.py` (~16 tests) | ✅ |
| `runtime/executor.py` | 48% | 98% | `tests/unit/test_executor.py` (~22 tests) | ✅ |
| `core/agent.py` | 73% | 97% | `tests/unit/test_agent.py` (extended, ~25 new tests) | ✅ |

### Remaining Gaps (optional — not needed for 80% target)

| Module | Coverage | Notes |
|--------|----------|-------|
| `skills/loader.py` | 45% | Largest remaining gap; dir-skill loading, reload, `unload_all` |
| `runtime/sandbox/docker_provider.py` | 52% | Docker sandbox (low priority, infra) |
| `memory/stores/sqlite.py` | 64% | `ChromaDBStore` untested (skip if chromadb not installed) |
| `memory/long_term/compactor.py` | 67% | Legacy `MemoryCompactor` paths |
| `memory/long_term/vector_memory.py` | 68% | `VectorMemory` store/retrieve paths |
| `memory/manager.py` | 71% | Session-keyed memory, compaction paths |
| `memory/git_sync.py` | 73% | Git commit / push error paths |
| `core/tools/registry.py` | 78% | `list_by_category`, `unregister` |

### Infrastructure Modules — Omit from Coverage

These modules require live external services or complex runtime setup and are intentionally excluded:

- `channels/discord_bot.py`
- `web/api/app.py`
- `cli/` (all files)
- `core/llm/litellm_provider.py`
- `automation/scheduler.py`
- `automation/heartbeat.py`
- `runtime/lifecycle.py`
- `utils/logging.py`
- `utils/events.py`
- `skills/builtin/news_digest.py`
- `__main__.py`
- `runtime/config.py`

### CI/CD ✅

| Task | Status | Notes |
|------|--------|-------|
| Write `.github/workflows/ci.yml` | ✅ | Python 3.11 + 3.12 matrix; checkout → pip install → pytest with coverage → upload artifact |

---

## Phase 3 — Web Console Enhancements

### Session 3 — Interactive Config Panel ✅

| Task | Status | File(s) |
|------|--------|---------|
| `PATCH /api/config` endpoint | ✅ | `hivecore/web/api/app.py` |
| Validate field names + Pydantic re-parse on save | ✅ | `hivecore/web/api/app.py` |
| Persist changes to `~/.hivecore/config.toml` via `save_settings()` | ✅ | `hivecore/web/api/app.py` |
| Handle `section="root"` for top-level scalars | ✅ | `hivecore/web/api/app.py` |
| Handle `section="channels"` nested sub-models | ✅ | `hivecore/web/api/app.py` |
| Redact `api_key` / `token` in PATCH response | ✅ | `hivecore/web/api/app.py` |
| `updateConfig()` in `src/lib/api.ts` | ✅ | `frontend/src/lib/api.ts` |
| Rewrite `ConfigPage.tsx` as interactive form | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Boolean toggle switches | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Number inputs with type coercion | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Password inputs with show/hide for sensitive fields | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Array / list fields as comma-separated textarea | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Per-section Save + Reset buttons | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| "unsaved" badge, spinner, "✓ saved" / error feedback | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Reload button to re-fetch config from disk | ✅ | `frontend/src/pages/ConfigPage.tsx` |
| Frontend rebuilt (`npm run build`) | ✅ | `hivecore/web/static/` |

---

## Phase 3 — Future Roadmap (not started)

> See `FUTURE_ROADMAP.md` for full details.

| Feature | Target Version | Status |
|---------|---------------|--------|
| Docker sandboxing (full) | v0.2.0 | ⬜ |
| Multi-agent support | v0.2.0 | ⬜ |
| MCP (Model Context Protocol) client/server | v0.2.0 | ⬜ |
| Skill Marketplace / Registry | v0.3.0 | ⬜ |
| Skill Pipelines / DAGs | v0.3.0 | ⬜ |
| Event-driven triggers | v0.3.0 | ⬜ |
| Agent personas / profiles | v0.3.0 | ⬜ |
| Kubernetes / cloud deployment | v0.4.0 | ⬜ |
| Knowledge graphs | v0.4.0 | ⬜ |
| Observability dashboard | v0.4.0 | ⬜ |
| Voice / real-time interaction | v0.5.0 | ⬜ |
| Multimodal support | v0.5.0 | ⬜ |

---

## Session 4 — Port Configuration & Startup Fix

| Task | Status | Notes |
|------|--------|-------|
| Diagnose `[WinError 10048]` port conflict | ✅ | Stale process from previous run held port 8088 |
| Kill stale process on port 8088 | ✅ | `taskkill /PID <pid> /F` via `netstat -ano` lookup |
| Confirm `WebSettings.host/port` already in settings model | ✅ | `hivecore/config/settings.py` — `WebSettings.port: int = 8088` |
| Confirm `lifecycle.py` already accepts `host`/`port` params | ✅ | `start_workstation(host, port, ...)` passes to `_start_web_server` |
| Confirm `hivecore start` already has `--host`/`--port` CLI flags | ✅ | `hivecore/cli/main.py` — `typer.Option("127.0.0.1")` / `typer.Option(8088)` |
| Change port via config file | ✅ | Set `[web] port = <number>` in `~/.hivecore/config.toml` |
| Override port at runtime | ✅ | `hivecore start --port 9000` |

---

## Known Issues / Gotchas

- **Windows file locking**: Calling `pytest.skip()` inside a `with tempfile.TemporaryDirectory()` block before `await mgr.close()` causes `PermissionError` because SQLite keeps the file open. Always close the manager before skipping.
- **`asyncio_mode = "auto"`**: The `PytestConfigWarning: Unknown config option` from pytest 9.0.2 is benign — works correctly with pytest-asyncio 1.3.0.
- **`FunctionTool.execute()` re-raises exceptions**: It no longer swallows errors. Tests must use `pytest.raises()` instead of checking error strings.
- **`rank_bm25` + `aiosqlite`**: Must be installed separately. Run `pip install -e ".[dev]"` to get all deps.
- **DuckDB shadow index**: Optional dep — tests skip gracefully when DuckDB is not installed.
- **`tomli-w`**: Was missing from dev environment; install with `pip install tomli-w`.
- **`SubprocessProvider`**: Is an alias for `SubprocessSandbox` at the bottom of `subprocess.py`.
- **`_settings_to_dict`**: Replaced with recursive `_clean_for_toml()` that strips `None` values (TOML has no null type).
- **Port conflict `[WinError 10048]`**: Occurs when a previous HiveCore process is still holding port 8088. Find the PID with `netstat -ano | findstr :8088` and kill it with `taskkill /PID <pid> /F`. To avoid future conflicts, set a different port in `~/.hivecore/config.toml` under `[web]` or pass `--port` to `hivecore start`.
