from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.chat_routes import router as chat_router
from app.api.govern_routes import router as govern_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings

_WEB_DIR = Path(__file__).resolve().parent / "web"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(govern_router)
    if _WEB_DIR.is_dir():
        app.mount("/console", StaticFiles(directory=_WEB_DIR, html=True), name="console")

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "trust-rag-enterprise-qa",
            "name": settings.app_name,
            "version": settings.app_version,
            "docs_url": "/docs",
            "task_plan_version": settings.task_plan_version,
        }

    return app


app = create_app()
