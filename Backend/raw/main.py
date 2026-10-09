import logging
import traceback
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import models
from .config import settings
from .database import SessionLocal
from .routes import auth, comments, events, notification, projects, tasks, users, ws

logger = logging.getLogger(__name__)
app = FastAPI(title="Role Based Project API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (auth.router, users.router, projects.router, tasks.router, comments.router,
               notification.router, events.router, ws.router):
    app.include_router(router)


def error_response(status_code: int, message: str, request_id: str | None = None, details=None):
    body = {"error": {"message": message}}
    if request_id:
        body["error"]["request_id"] = request_id
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    return error_response(exc.status_code, message, details=None if isinstance(exc.detail, str) else exc.detail)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return error_response(422, "Please check the highlighted fields.", details=exc.errors())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    request_id = str(uuid.uuid4())
    logger.exception("Unhandled request error id=%s", request_id)
    db = SessionLocal()
    try:
        db.add(models.ErrorLog(
            request_id=request_id, method=request.method, path=request.url.path, status_code=500,
            error_type=type(exc).__name__, message=str(exc), traceback="".join(traceback.format_exception(exc)),
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not persist error log id=%s", request_id)
    finally:
        db.close()
    return error_response(500, "Something went wrong. Please try again.", request_id=request_id)
