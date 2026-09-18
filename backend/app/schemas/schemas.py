from datetime import datetime
from pydantic import BaseModel, Field

from app.services.hold_status import STATUS_LABELS


class HallOut(BaseModel):
    id: int
    name: str
    rows: int
    cols: int
    aisle_cols: list[int]
    model_config = {"from_attributes": True}


class ShowtimeOut(BaseModel):
    id: int
    hall_id: int
    film_title: str
    start_at: datetime
    hall_name: str | None = None
    model_config = {"from_attributes": True}


class HoldOut(BaseModel):
    id: int
    showtime_id: int
    order_code: str
    row: int
    start_col: int
    end_col: int
    party_size: int
    status: str
    status_label: str
    cancel_reason: str | None = None
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, h) -> "HoldOut":
        return cls(
            id=h.id,
            showtime_id=h.showtime_id,
            order_code=h.order_code,
            row=h.row,
            start_col=h.start_col,
            end_col=h.end_col,
            party_size=h.party_size,
            status=h.status,
            status_label=STATUS_LABELS.get(h.status, h.status),
            cancel_reason=h.cancel_reason,
            cancelled_at=h.cancelled_at,
            created_at=h.created_at,
        )


class HoldRequest(BaseModel):
    showtime_id: int
    party_size: int = Field(ge=1, le=12)
    preferred_row: int | None = None


class CancelRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


class ConflictOut(BaseModel):
    id: int
    showtime_id: int
    party_size: int
    reason: str
    created_at: datetime
    model_config = {"from_attributes": True}


class SeatMapCell(BaseModel):
    row: int
    col: int
    is_aisle: bool
    occupied: bool
    heat: float


class SeatMapOut(BaseModel):
    showtime_id: int
    hall_name: str
    rows: int
    cols: int
    cells: list[SeatMapCell]
