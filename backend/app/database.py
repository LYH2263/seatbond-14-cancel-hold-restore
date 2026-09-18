from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings

_engine_kwargs: dict = {}
if settings.database_url.startswith("sqlite"):
    # 测试用内存库：跨线程共享同一连接，避免每个连接各开一份空库
    _engine_kwargs = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
engine = create_engine(settings.database_url, pool_pre_ping=True, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def ensure_hold_schema() -> None:
    """对既有库做幂等结构补齐（仓库未引入迁移工具）。

    - seat_holds 增加取消相关列（取消原因、取消时间）；
    - 旧的整表唯一约束 uq_hold_span 会让「取消留痕 + 原坐标重新锁座」冲突，
      替换为仅覆盖持有中记录的部分唯一索引 uq_hold_span_active。
    """
    insp = inspect(engine)
    if "seat_holds" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("seat_holds")}
    with engine.begin() as conn:
        if "cancel_reason" not in cols:
            conn.execute(text("ALTER TABLE seat_holds ADD COLUMN cancel_reason VARCHAR(200)"))
        if "cancelled_at" not in cols:
            conn.execute(text("ALTER TABLE seat_holds ADD COLUMN cancelled_at TIMESTAMP"))
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE seat_holds DROP CONSTRAINT IF EXISTS uq_hold_span"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_hold_span_active "
                "ON seat_holds (showtime_id, row, start_col, end_col) "
                "WHERE status = 'held'"
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
