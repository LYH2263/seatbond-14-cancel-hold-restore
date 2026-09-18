from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# 持座状态：held 为唯一活跃态；cancelled / released 均为终态。
# 座位图、连座搜索、冲突检测只认 held —— 终态格子一律按空闲处理。
HOLD_STATUS_HELD = "held"
HOLD_STATUS_CANCELLED = "cancelled"
HOLD_STATUS_RELEASED = "released"  # 超时释放（仓内可能已存在此类终态行）
HOLD_STATUSES = (HOLD_STATUS_HELD, HOLD_STATUS_CANCELLED, HOLD_STATUS_RELEASED)
TERMINAL_HOLD_STATUSES = (HOLD_STATUS_CANCELLED, HOLD_STATUS_RELEASED)


class Hall(Base):
    __tablename__ = "halls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    aisle_cols: Mapped[str] = mapped_column(String(80), default="")  # comma-separated
    showtimes: Mapped[list["Showtime"]] = relationship(back_populates="hall")


class Showtime(Base):
    __tablename__ = "showtimes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hall_id: Mapped[int] = mapped_column(ForeignKey("halls.id"))
    film_title: Mapped[str] = mapped_column(String(120))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    hall: Mapped[Hall] = relationship(back_populates="showtimes")
    holds: Mapped[list["SeatHold"]] = relationship(back_populates="showtime")


class SeatHold(Base):
    __tablename__ = "seat_holds"
    # 同一坐标跨度最多一条「持有中」记录；取消/释放的历史行保留用于对账，
    # 不占用唯一位，原坐标因此可以被新锁座重新占到。
    __table_args__ = (
        Index(
            "uq_hold_span_active",
            "showtime_id",
            "row",
            "start_col",
            "end_col",
            unique=True,
            postgresql_where=text(f"status = '{HOLD_STATUS_HELD}'"),
            sqlite_where=text(f"status = '{HOLD_STATUS_HELD}'"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    showtime_id: Mapped[int] = mapped_column(ForeignKey("showtimes.id"))
    order_code: Mapped[str] = mapped_column(String(40))
    row: Mapped[int] = mapped_column(Integer)
    start_col: Mapped[int] = mapped_column(Integer)
    end_col: Mapped[int] = mapped_column(Integer)
    party_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=HOLD_STATUS_HELD)
    cancel_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    showtime: Mapped[Showtime] = relationship(back_populates="holds")


class ConflictLog(Base):
    __tablename__ = "conflict_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    showtime_id: Mapped[int] = mapped_column(ForeignKey("showtimes.id"))
    party_size: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
