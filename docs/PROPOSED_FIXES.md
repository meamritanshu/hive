# HiveCore — Proposed Solutions & Architectural Fixes

This document outlines strategic solutions and technical fixes to address the risks and flaws identified in the HiveCore Project Overview.

## 1. Hardening the "Skill" System
*   **Virtual Environment Isolation**: Use a tool like `uv` or `venv` to automatically create a dedicated virtual environment for each skill. Support a "Requirements Header" in the script (e.g., `# Requirements: requests, beautifulsoup4`) that HiveCore parses and installs on first run.
*   **Credential Vaulting**: Never expose `config.toml` to the skill subprocess. Instead, provide a **Restricted Context Object**. When a skill is executed, HiveCore should only pass the specific API keys or environment variables that the skill explicitly requests via a manifest or decorator (e.g., `@tool(needs_keys=["OPENAI_API_KEY"])`).
*   **Capability-Based Security**: Implement a "Permission" system for skills. By default, skills should have no network access or write access to the `~/.hivecore/` directory unless explicitly granted in a `skill_name.toml` file.

## 2. Improving Scalability & Performance
*   **Shadow Indexing (Tantivy/DuckDB)**: Keep Markdown as the "source of truth" for humans, but maintain a high-performance **Shadow Index** using a library like [Tantivy](https://github.com/quickwit-oss/tantivy) or [DuckDB](https://duckdb.org/). This allows the `HybridRetriever` to query millions of lines in milliseconds without reading physical `.md` files every time.
*   **Hierarchical Summarization**: Instead of a single `MemoryCompactor`, use a "Tiered Memory" approach:
    *   **Tier 1 (Raw)**: Last 7 days of episodic logs (full detail).
    *   **Tier 2 (Condensed)**: Weekly summaries (lossy).
    *   **Tier 3 (Entities)**: Extract "Knowledge Graphs" (People, Places, Facts) from logs and move them to `knowledge/personal.md` permanently.

## 3. Mitigating Single-Agent Weaknesses
*   **Reflection & Self-Correction**: Add a "Critic" step to the ReAct loop. After 3 unsuccessful tool calls, the agent should be forced to perform a `Self-Reflection` action: *"Why is this failing? Is my search query too broad? Am I using the wrong tool?"* This prevents infinite loops.
*   **Session-Aware Context**: Move `ShortTermMemory` from a global state to a **Session-Keyed Store**. Use a unique ID for `discord_channel_123` vs `cli_local`. The agent can "cross-load" memories from the vector store, but the immediate conversation window remains clean and relevant to the current channel.

## 4. Enhancing Usability & Sync
*   **Git-Integrated Memory**: Automatically initialize `~/.hivecore/` as a Git repository. 
    *   **Benefit 1**: Every "Compaction" or user edit creates a commit, allowing for "Undo" functionality.
    *   **Benefit 2**: Users can sync across devices by simply adding a private GitHub/GitLab remote and running `git pull/push`.
*   **Markdown Schema Validation**: Use a Pydantic-based linter to validate the structure of `knowledge/` files. If a user manually edits a file and breaks the format, HiveCore should flag the error in the Web Console and offer to "Auto-Fix" the Markdown structure.

## 5. Closing Architectural Gaps
*   **LanceDB for Local Vectors**: Swap the default SQLite vector implementation for [LanceDB](https://lancedb.com/). It is "local-first," requires no server (just files), and is significantly faster than SQLite for vector similarity search as the data scales.
*   **The "Execution Provider" Pattern**: Refactor the `HiveRuntime` to use an "Execution Provider" interface. 
    *   `SubprocessProvider` (Default/Lightweight)
    *   `DockerProvider` (High-security/Optional)
    *   Users can then toggle `sandbox_type = "docker"` in their config for specific high-risk skills.
