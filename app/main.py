import logging
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import api, auth
from app.core.database import engine, get_db
from app.features import reschedule

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    engine.dispose()


app = FastAPI(
    title="Booking Engine API",
    version="1.0.0",
    description="Timezone-aware schedules and PostgreSQL-enforced, conflict-free bookings.",
    lifespan=lifespan,
)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(api.router, prefix="/api/v1")
app.include_router(reschedule.router, prefix="/api/v1")


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid4())
    start = perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        (perf_counter() - start) * 1000,
    )
    return response


@app.get("/health", tags=["Operations"])
def health():
    return {"status": "ok"}


@app.get("/ready", tags=["Operations"])
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ready"}
