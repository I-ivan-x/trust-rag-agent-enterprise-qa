from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.include_router(health_router)

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

