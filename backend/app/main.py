"""Application factory."""

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import app_error_handler, router
from app.db import make_engine, migrate
from app.errors import AppError


def _load_env_file() -> None:
    path = Path('.env')
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip())


def create_app(
    database_path: str | None = None,
    cookie_secure: bool | None = None,
    session_days: int | None = None,
) -> FastAPI:
    """Build the API against one SQLite file."""
    _load_env_file()
    path = database_path or os.environ.get('DATABASE_PATH', 'data/yoyo.db')
    resolved = str(Path(path).resolve())
    migrate(resolved)
    if cookie_secure is None:
        cookie_secure = os.environ.get('COOKIE_SECURE', '0') == '1'
    if session_days is None:
        session_days = int(os.environ.get('SESSION_DAYS', '30'))
    app = FastAPI(title='悠悠课程本')
    app.state.engine = make_engine(resolved)
    app.state.database_path = resolved
    app.state.cookie_secure = cookie_secure
    app.state.session_days = session_days
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation)
    app.include_router(router)
    return app


def _validation(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={'detail': {'code': 'invalid', 'message': '请检查填写的内容'}},
    )
