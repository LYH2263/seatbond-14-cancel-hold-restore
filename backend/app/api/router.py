from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import ConflictLog, Hall, SeatHold, Showtime
from app.schemas.schemas import (
    CancelRequest,
    ConflictOut,
    HallOut,
    HoldOut,
    HoldRequest,
    SeatMapCell,
    SeatMapOut,
    ShowtimeOut,
)
from app.services.bond_engine import (
    HoldSpan,
    SeatCell,
    conflicts_with,
    find_bond_across_rows,
    find_contiguous_block,
)
from app.services.hold_status import (
    STATUS_CANCELLED,
    STATUS_HELD,
    STATUS_LABELS,
    STATUS_RELEASED,
    is_terminal,
)

api_router = APIRouter()

# 列表/座位图/搜索三处共用的「空闲」口径：只有 held 占座，两种终态都按空闲。
_FILTERABLE_STATUSES = (STATUS_HELD, STATUS_CANCELLED, STATUS_RELEASED)


def _aisles(hall: Hall) -> list[int]:
    if not hall.aisle_cols.strip():
        return []
    return [int(x) for x in hall.aisle_cols.split(",") if x.strip()]


def _hall_out(h: Hall) -> HallOut:
    return HallOut(id=h.id, name=h.name, rows=h.rows, cols=h.cols, aisle_cols=_aisles(h))


def _active_holds(db: Session, showtime_id: int) -> list[SeatHold]:
    """某场次当前真正占座的持座（仅 held）。座位图与锁座搜索统一走这里。"""
    return list(
        db.scalars(
            select(SeatHold).where(
                SeatHold.showtime_id == showtime_id,
                SeatHold.status == STATUS_HELD,
            )
        ).all()
    )


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/halls", response_model=list[HallOut])
def list_halls(db: Session = Depends(get_db)):
    return [_hall_out(h) for h in db.scalars(select(Hall).order_by(Hall.id)).all()]


@api_router.get("/showtimes", response_model=list[ShowtimeOut])
def list_showtimes(db: Session = Depends(get_db)):
    rows = db.scalars(select(Showtime).order_by(Showtime.start_at)).all()
    out = []
    for s in rows:
        hall = db.get(Hall, s.hall_id)
        out.append(
            ShowtimeOut(
                id=s.id,
                hall_id=s.hall_id,
                film_title=s.film_title,
                start_at=s.start_at,
                hall_name=hall.name if hall else None,
            )
        )
    return out


@api_router.get("/seatmap/{showtime_id}", response_model=SeatMapOut)
def seatmap(showtime_id: int, db: Session = Depends(get_db)):
    st = db.get(Showtime, showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    occupied: set[tuple[int, int]] = set()
    # 已取消/超时释放的格子立即按空闲展示，热力随之清空。
    for h in _active_holds(db, showtime_id):
        for c in range(h.start_col, h.end_col + 1):
            occupied.add((h.row, c))
    cells: list[SeatMapCell] = []
    for r in range(1, hall.rows + 1):
        for c in range(1, hall.cols + 1):
            occ = (r, c) in occupied
            cells.append(
                SeatMapCell(
                    row=r,
                    col=c,
                    is_aisle=c in aisles,
                    occupied=occ,
                    heat=1.0 if occ else (0.15 if c in aisles else 0.0),
                )
            )
    return SeatMapOut(
        showtime_id=showtime_id,
        hall_name=hall.name,
        rows=hall.rows,
        cols=hall.cols,
        cells=cells,
    )


@api_router.get("/holds", response_model=list[HoldOut])
def list_holds(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(SeatHold).order_by(SeatHold.id.desc())
    if status is not None:
        if status not in _FILTERABLE_STATUSES:
            allowed = ", ".join(_FILTERABLE_STATUSES)
            raise HTTPException(422, f"不支持的状态筛选：{status}（可选 {allowed}）")
        stmt = stmt.where(SeatHold.status == status)
    rows = db.scalars(stmt).all()
    return [HoldOut.from_model(h) for h in rows]


@api_router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.post("/holds", response_model=HoldOut)
def create_hold(body: HoldRequest, db: Session = Depends(get_db)):
    st = db.get(Showtime, body.showtime_id)
    if not st:
        raise HTTPException(404, "场次不存在")
    hall = db.get(Hall, st.hall_id)
    assert hall
    aisles = set(_aisles(hall))
    # 终态持座不占座：取消/释放后的原坐标可被新锁座重新占到。
    existing = _active_holds(db, body.showtime_id)
    holds = [HoldSpan(row=h.row, start_col=h.start_col, end_col=h.end_col) for h in existing]
    seats_by_row: dict[int, list[SeatCell]] = {}
    for r in range(1, hall.rows + 1):
        seats_by_row[r] = [
            SeatCell(row=r, col=c, is_aisle=c in aisles) for c in range(1, hall.cols + 1)
        ]

    block = None
    if body.preferred_row:
        block = find_contiguous_block(
            seats_by_row.get(body.preferred_row, []), holds, body.preferred_row, body.party_size
        )
    if block is None:
        block = find_bond_across_rows(seats_by_row, holds, body.party_size)
    if block is None:
        db.add(
            ConflictLog(
                showtime_id=body.showtime_id,
                party_size=body.party_size,
                reason=f"无足够连续空座（人数 {body.party_size}）",
            )
        )
        db.commit()
        raise HTTPException(409, "无足够连续空座")

    hits = conflicts_with(holds, block)
    if hits:
        db.add(
            ConflictLog(
                showtime_id=body.showtime_id,
                party_size=body.party_size,
                reason=f"与既有持座重叠：第{hits[0].row}排 {hits[0].start_col}-{hits[0].end_col}",
            )
        )
        db.commit()
        raise HTTPException(409, "与既有持座冲突")

    code = f"SB-{int(datetime.utcnow().timestamp()) % 100000:05d}"
    hold = SeatHold(
        showtime_id=body.showtime_id,
        order_code=code,
        row=block.row,
        start_col=block.start_col,
        end_col=block.end_col,
        party_size=body.party_size,
    )
    db.add(hold)
    try:
        db.commit()
    except IntegrityError:
        # 并发下另一请求已占到同坐标（部分唯一索引兜底）。
        db.rollback()
        raise HTTPException(409, "与既有持座冲突")
    db.refresh(hold)
    return HoldOut.from_model(hold)


@api_router.post("/holds/{hold_id}/cancel", response_model=HoldOut)
def cancel_hold(hold_id: int, body: CancelRequest | None = None, db: Session = Depends(get_db)):
    hold = db.get(SeatHold, hold_id)
    if not hold:
        raise HTTPException(404, "持座记录不存在")
    reason = (body.reason.strip() if body and body.reason else "")

    if hold.status == STATUS_CANCELLED:
        raise HTTPException(409, f"持座 {hold.order_code} 已取消，不能重复取消")
    if hold.status == STATUS_RELEASED:
        raise HTTPException(409, f"持座 {hold.order_code} 已超时释放，不能取消")
    if is_terminal(hold.status):
        raise HTTPException(409, f"持座 {hold.order_code} 已处于终态（{STATUS_LABELS.get(hold.status, hold.status)}），不能取消")

    hold.status = STATUS_CANCELLED
    hold.cancel_reason = reason or None
    hold.cancelled_at = datetime.utcnow()
    db.commit()
    db.refresh(hold)
    return HoldOut.from_model(hold)
