from collections.abc import Generator

from app.core.config import Settings, get_settings


def get_app_settings() -> Generator[Settings, None, None]:
    yield get_settings()

