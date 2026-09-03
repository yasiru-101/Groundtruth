"""FastAPI app that serves the Groundtruth dashboard API and static SPA."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from groundtruth.api.jobs import JobStore
from groundtruth.api.repository import ArtifactRepository
from groundtruth.api.routers import agents, board, discrepancies, integrity, jobs, meta, runs, score
from groundtruth.api.settings import ApiSettings


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    settings = settings or ApiSettings()
    repo = ArtifactRepository(settings.artifacts_dir)
    job_store = JobStore(settings)

    app = FastAPI(title="Groundtruth Dashboard", version="0.1.0")
    app.state.settings = settings
    app.state.repo = repo
    app.state.job_store = job_store

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(meta.router)
    app.include_router(runs.router)
    app.include_router(score.router)
    app.include_router(discrepancies.router)
    app.include_router(board.router)
    app.include_router(integrity.router)
    app.include_router(agents.router)
    app.include_router(jobs.router)

    # SPA static mount + fallback.
    static_dir = settings.static_dir
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def serve_spa(request: Request, full_path: str) -> FileResponse:
            # API paths are handled by routers above; this only catches non-API routes.
            if request.url.path.startswith("/api/"):
                return JSONResponse({"detail": "not found"}, status_code=404)
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse({"detail": "frontend not built"}, status_code=404)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=500)

    return app
