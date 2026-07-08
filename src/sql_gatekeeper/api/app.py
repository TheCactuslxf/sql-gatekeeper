from fastapi import FastAPI

from sql_gatekeeper.api.routes import router
from sql_gatekeeper.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(router)
    return app


app = create_app()

