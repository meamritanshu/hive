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
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hivecore import __version__
from hivecore.config.settings import HiveSettings

# Path to the built frontend static files
STATIC_DIR = Path(__file__).parent.parent / "static"

logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    conversation_id: str


class ConfigUpdateRequest(BaseModel):
    key: str
    value: Any


def create_app(agent: Any = None, settings: Optional[HiveSettings] = None) -> FastAPI:
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
        config = settings.model_dump()
        # Redact sensitive values
        if config.get("llm", {}).get("api_key"):
            config["llm"]["api_key"] = "***"
        for ch in config.get("channels", {}).values():
            if isinstance(ch, dict) and ch.get("token"):
                ch["token"] = "***"
        return JSONResponse(config)

    @app.get("/api/scheduler/jobs")
    async def list_jobs() -> JSONResponse:
        """List scheduled jobs."""
        # TODO: integrate with scheduler instance
        return JSONResponse({"jobs": []})

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
