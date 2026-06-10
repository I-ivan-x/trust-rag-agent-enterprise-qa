from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_app_settings
from app.core.config import Settings

router = APIRouter()
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@router.get("/health")
def health(settings: SettingsDep) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": "trust-rag-enterprise-qa",
        "version": settings.app_version,
        "environment": settings.environment,
        "mock_mode": settings.mock_mode,
        "task_plan_version": settings.task_plan_version,
    }
