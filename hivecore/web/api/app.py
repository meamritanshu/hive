"""FastAPI application for the HiveCore web console.

Provides REST and WebSocket APIs for:
- Chat interaction with the agent
- Configuration management
- Skill management
- Memory viewing and search
- Scheduler management
- System status and observability
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hivecore import __version__
from hivecore.config.settings import HiveSettings, save_settings

# Path to the built frontend static files
STATIC_DIR = Path(__file__).parent.parent / "static"

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str


class ConfigUpdateRequest(BaseModel):
    """Payload for a config section update.

    ``section`` is a top-level key of HiveSettings (e.g. ``"llm"``, ``"memory"``).
    ``updates`` is a dict of field-name → new-value for that section.
    Top-level scalar fields (``data_dir``, ``log_level``) can be updated by
    using ``section="root"`` and the field name in ``updates``.
    """

    section: str
    updates: dict[str, Any]


def create_app(agent: Any = None, settings: HiveSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        agent: The Agent instance.
        settings: HiveCore settings.

    Returns:
        Configured FastAPI app.
    """
    app = FastAPI(
        title="HiveCore",
        description="HiveCore Workstation API",
        version=__version__,
    )

    settings = settings or HiveSettings()

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.web.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- REST endpoints ---

    @app.get("/api/status")
    async def get_status() -> JSONResponse:
        """Get workstation status."""
        return JSONResponse({
            "status": "running",
            "version": __version__,
            "model": settings.llm.model,
            "provider": settings.llm.provider,
            "memory_backend": settings.memory.backend,
        })

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> ChatResponse:
        """Send a message to the agent and get a response."""
        if not agent:
            return ChatResponse(response="Agent not initialized", conversation_id="")

        response = await agent.run(request.message)
        return ChatResponse(
            response=response.content,
            conversation_id=request.conversation_id or "default",
        )

    @app.get("/api/memory/stats")
    async def memory_stats() -> JSONResponse:
        """Get memory system statistics."""
        if not agent:
            return JSONResponse({"error": "Agent not initialized"})

        stats = await agent.memory_stats()
        try:
            return JSONResponse(json.loads(stats))
        except json.JSONDecodeError:
            return JSONResponse({"raw": stats})

    @app.get("/api/memory/search")
    async def memory_search(q: str, top_k: int = 10) -> JSONResponse:
        """Search the agent's memory."""
        if not agent or not agent._memory_manager:
            return JSONResponse({"results": []})

        results = await agent._memory_manager.retrieve(q, top_k=top_k)
        return JSONResponse({"results": results})

    @app.get("/api/skills")
    async def list_skills() -> JSONResponse:
        """List installed skills."""
        if not agent:
            return JSONResponse({"skills": []})

        tools = agent._tools.get_definitions()
        return JSONResponse({
            "skills": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "parameters": [p.model_dump() for p in t.parameters],
                }
                for t in tools
            ]
        })

    @app.get("/api/config")
    async def get_config() -> JSONResponse:
        """Get current configuration (sensitive values redacted)."""
        from fastapi.encoders import jsonable_encoder
        config = jsonable_encoder(settings)
        # Redact sensitive values
        if config.get("llm", {}).get("api_key"):
            config["llm"]["api_key"] = "***"
        for ch in config.get("channels", {}).values():
            if isinstance(ch, dict) and ch.get("token"):
                ch["token"] = "***"
        return JSONResponse(config)

    # Section names that map directly to sub-models on HiveSettings
    _SUBSECTIONS = {"llm", "memory", "skills", "web", "channels", "scheduler", "agent"}

    @app.patch("/api/config")
    async def update_config(req: ConfigUpdateRequest) -> JSONResponse:
        """Update one section of the configuration and persist to disk.

        The in-memory ``settings`` object is mutated in-place so the running
        server reflects the new values immediately (no restart needed for most
        options).  The new values are also written to ``~/.hivecore/config.toml``.

        Returns the updated section (with sensitive fields redacted).
        """
        from fastapi.encoders import jsonable_encoder

        section = req.section.lower()

        # ── root-level scalar fields ──────────────────────────────────────────
        if section == "root":
            allowed_root = {"data_dir", "log_level"}
            unknown = set(req.updates) - allowed_root
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown root-level field(s): {sorted(unknown)}",
                )
            for key, val in req.updates.items():
                try:
                    # Validate through a temporary copy
                    candidate = settings.model_copy(update={key: val})
                    object.__setattr__(settings, key, getattr(candidate, key))
                except Exception as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            save_settings(settings)
            return JSONResponse({"section": "root", "updated": list(req.updates)})

        # ── sub-model sections ────────────────────────────────────────────────
        if section not in _SUBSECTIONS:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Unknown config section '{section}'. "
                    f"Valid sections: {sorted(_SUBSECTIONS | {'root'})}"
                ),
            )

        sub_model = getattr(settings, section)

        # For the 'channels' section the value must be a nested dict
        # (e.g. {"discord": {"enabled": true}}).  We handle each channel
        # sub-model individually.
        if section == "channels":
            channel_names = {"discord", "telegram", "imessage"}
            unknown_channels = set(req.updates) - channel_names
            if unknown_channels:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown channel(s): {sorted(unknown_channels)}",
                )
            for ch_name, ch_updates in req.updates.items():
                if not isinstance(ch_updates, dict):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Value for channel '{ch_name}' must be an object.",
                    )
                ch_model = getattr(sub_model, ch_name)
                try:
                    updated_ch = ch_model.model_copy(update=ch_updates)
                    # Validate by re-parsing
                    updated_ch = type(ch_model)(**updated_ch.model_dump())
                    object.__setattr__(sub_model, ch_name, updated_ch)
                except Exception as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
            save_settings(settings)
            result = jsonable_encoder(sub_model)
            for ch in result.values():
                if isinstance(ch, dict) and ch.get("token"):
                    ch["token"] = "***"
            return JSONResponse({"section": section, "updated": result})

        # Standard sub-model: validate field names then apply
        valid_fields = set(sub_model.model_fields)
        unknown_fields = set(req.updates) - valid_fields
        if unknown_fields:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown field(s) for section '{section}': {sorted(unknown_fields)}",
            )

        try:
            updated_sub = sub_model.model_copy(update=req.updates)
            # Re-validate through the model constructor (runs field validators)
            updated_sub = type(sub_model)(**updated_sub.model_dump())
            object.__setattr__(settings, section, updated_sub)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        save_settings(settings)

        result = jsonable_encoder(updated_sub)
        # Redact api_key in LLM section response
        if section == "llm" and result.get("api_key"):
            result["api_key"] = "***"
        return JSONResponse({"section": section, "updated": result})

    @app.get("/api/scheduler/jobs")
    async def list_jobs() -> JSONResponse:
        """List scheduled jobs."""
        # TODO: integrate with scheduler instance
        return JSONResponse({"jobs": []})

    @app.post("/api/restart")
    async def restart_server() -> JSONResponse:
        """Gracefully restart the HiveCore server process.

        Sends SIGTERM to the current process after a short delay so the HTTP
        response can be flushed to the client first.  On Windows the process
        exits and must be restarted manually (or via a process supervisor).
        """
        import os
        import signal

        async def _shutdown() -> None:
            await asyncio.sleep(0.6)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.create_task(_shutdown())
        return JSONResponse({"status": "restarting"})

    # --- WebSocket for streaming chat ---

    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket) -> None:
        """WebSocket endpoint for streaming chat."""
        await websocket.accept()

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                user_input = message.get("message", "")

                if not user_input or not agent:
                    await websocket.send_json({"error": "Invalid request"})
                    continue

                # Stream response
                async for chunk in agent.run_stream(user_input):
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk,
                    })

                # Signal completion
                await websocket.send_json({"type": "done"})

        except WebSocketDisconnect:
            logger.debug("WebSocket client disconnected")
        except Exception as e:
            logger.error("WebSocket error: %s", e)
            try:
                await websocket.send_json({"type": "error", "error": str(e)})
            except Exception:
                pass

    # --- Serve frontend static files ---

    if STATIC_DIR.is_dir():
        # Serve static assets (JS, CSS, images)
        app.mount(
            "/assets",
            StaticFiles(directory=str(STATIC_DIR / "assets")),
            name="static-assets",
        )

        # Serve favicon and other root-level static files
        @app.get("/hive.svg")
        async def favicon() -> FileResponse:
            return FileResponse(STATIC_DIR / "hive.svg")

        # SPA catch-all: serve index.html for all non-API routes
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            # If the file exists in static dir, serve it directly
            file_path = STATIC_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            # Otherwise, serve index.html for SPA routing
            return FileResponse(STATIC_DIR / "index.html")

    return app
