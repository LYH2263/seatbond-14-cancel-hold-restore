"""取消持座端到端测例：列表、座位图、搜索三处共享同一「空闲」口径。"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import Hall, SeatHold, Showtime
from app.services.hold_status import (
    STATUS_CANCELLED,
    STATUS_HELD,
    STATUS_RELEASED,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    db = TestingSession()
    db.add(Hall(name="测试厅", rows=3, cols=10, aisle_cols=""))
    db.flush()
    db.add(
        Showtime(
            hall_id=1,
            film_title="测试片",
            start_at=datetime(2026, 9, 18, 20, 0),
        )
    )
    db.commit()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestingSession
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    return TestClient(app)


def _occupied_cells(client, sid):
    cells = client.get(f"/api/seatmap/{sid}").json()["cells"]
    return {(c["row"], c["col"]) for c in cells if c["occupied"]}


def test_cancelled_seat_can_be_re_locked_at_same_coords(client):
    sid = 1
    # 第一单落在最左侧：R1 C1-3
    h1 = client.post("/api/holds", json={"showtime_id": sid, "party_size": 3}).json()
    assert (h1["row"], h1["start_col"], h1["end_col"]) == (1, 1, 3)
    # 第二单顺延到 C4-6
    client.post("/api/holds", json={"showtime_id": sid, "preferred_row": 1, "party_size": 3})

    r = client.post(f"/api/holds/{h1['id']}/cancel", json={"reason": "观众改签"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == STATUS_CANCELLED
    assert body["status_label"] == "已取消"
    assert body["cancel_reason"] == "观众改签"
    assert body["cancelled_at"] is not None

    # 座位图立即视为空闲
    assert (1, 1) not in _occupied_cells(client, sid)

    # 新锁座应能重新占到原坐标 C1-3
    h3 = client.post(
        "/api/holds", json={"showtime_id": sid, "preferred_row": 1, "party_size": 3}
    ).json()
    assert (h3["row"], h3["start_col"], h3["end_col"]) == (1, 1, 3)
    assert h3["id"] != h1["id"]
    assert (1, 1) in _occupied_cells(client, sid)


def test_repeat_cancel_fails_with_clear_message(client):
    h = client.post("/api/holds", json={"showtime_id": 1, "party_size": 2}).json()
    first = client.post(f"/api/holds/{h['id']}/cancel", json={"reason": "首次取消"})
    assert first.status_code == 200

    second = client.post(f"/api/holds/{h['id']}/cancel", json={"reason": "再来一次"})
    assert second.status_code == 409
    assert "已取消" in second.json()["detail"]
    # 原因不被重复请求覆盖，行记录保留
    assert first.json()["cancel_reason"] == "首次取消"


def test_cancel_keeps_row_for_reconciliation_and_list_filters(client, db_session):
    h = client.post("/api/holds", json={"showtime_id": 1, "party_size": 2}).json()
    client.post(f"/api/holds/{h['id']}/cancel", json={"reason": "对账用"})

    held = client.get("/api/holds", params={"status": STATUS_HELD}).json()
    cancelled = client.get("/api/holds", params={"status": STATUS_CANCELLED}).json()
    all_rows = client.get("/api/holds").json()

    assert all(x["id"] != h["id"] for x in held)
    kept = [x for x in cancelled if x["id"] == h["id"]]
    assert len(kept) == 1
    assert kept[0]["cancel_reason"] == "对账用"
    assert any(x["id"] == h["id"] for x in all_rows)  # 全量列表仍保留终态行

    # 库里的行也确实还在
    db = db_session()
    try:
        row = db.scalars(select(SeatHold).where(SeatHold.id == h["id"])).one()
        assert row.status == STATUS_CANCELLED
        assert row.cancel_reason == "对账用"
    finally:
        db.close()


def test_released_hold_is_free_and_cannot_be_cancelled(client, db_session):
    # 直接造一条超时释放的终态记录（模拟超时释放任务）
    db = db_session()
    try:
        db.add(
            SeatHold(
                showtime_id=1,
                order_code="SB-TTL1",
                row=1,
                start_col=1,
                end_col=3,
                party_size=3,
                status=STATUS_RELEASED,
            )
        )
        db.commit()
        rid = db.scalars(select(SeatHold).where(SeatHold.order_code == "SB-TTL1")).one().id
    finally:
        db.close()

    # 座位图：释放格空闲
    assert _occupied_cells(client, 1) == set()

    # 搜索：新锁座可占到同样的坐标
    h = client.post("/api/holds", json={"showtime_id": 1, "party_size": 3}).json()
    assert (h["row"], h["start_col"], h["end_col"]) == (1, 1, 3)

    # 已释放再取消应失败，并与「已取消」区分提示
    r = client.post(f"/api/holds/{rid}/cancel", json={"reason": "想取消"})
    assert r.status_code == 409
    assert "超时释放" in r.json()["detail"]

    # 列表能区分两种终态
    released = client.get("/api/holds", params={"status": STATUS_RELEASED}).json()
    assert any(x["id"] == rid and x["status_label"] == "超时释放" for x in released)
    cancelled = client.get("/api/holds", params={"status": STATUS_CANCELLED}).json()
    assert all(x["id"] != rid for x in cancelled)


def test_cancel_unknown_and_active_only_rules(client):
    assert client.post("/api/holds/999/cancel", json={}).status_code == 404

    h = client.post("/api/holds", json={"showtime_id": 1, "party_size": 2}).json()
    # 空原因也允许取消
    r = client.post(f"/api/holds/{h['id']}/cancel", json={"reason": "   "})
    assert r.status_code == 200
    assert r.json()["cancel_reason"] is None

    # 非法筛选值
    assert client.get("/api/holds", params={"status": "nope"}).status_code == 422
