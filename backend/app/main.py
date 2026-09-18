from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _apply_light_migrations() -> None:
    """对既有库做小修补；create_all 不会 ALTER 已有表。

    旧版 seat_holds 上有覆盖全部状态的唯一约束 uq_hold_span，会让取消/释放后
    同坐标无法重新被占；新版改为仅 held 的部分唯一索引（见 models），旧约束需删除。
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE seat_holds DROP CONSTRAINT IF EXISTS uq_hold_span"))
        conn.execute(text("ALTER TABLE seat_holds ADD COLUMN IF NOT EXISTS cancel_reason VARCHAR(200)"))
        conn.execute(text("ALTER TABLE seat_holds ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_hold_span_active "
                "ON seat_holds (showtime_id, row, start_col, end_col) WHERE status = 'held'"
            )
        )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _apply_light_migrations()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="SeatBond", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
