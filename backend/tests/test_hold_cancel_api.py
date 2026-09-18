"""取消持座的端到端用例：列表、座位图、连座搜索对「空闲」的一致认知。"""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models.models import HOLD_STATUS_RELEASED, Hall, SeatHold, Showtime


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def _make_showtime() -> int:
    db = SessionLocal()
    try:
        hall = Hall(name="测试厅", rows=4, cols=8, aisle_cols="")
        db.add(hall)
        db.flush()
        st = Showtime(
            hall_id=hall.id,
            film_title="测试片",
            start_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(st)
        db.commit()
        return st.id
    finally:
        db.close()


def _insert_hold(**kwargs) -> int:
    db = SessionLocal()
    try:
        hold = SeatHold(**kwargs)
        db.add(hold)
        db.commit()
        return hold.id
    finally:
        db.close()


def _lock(client: TestClient, showtime_id: int, party_size: int, **extra):
    resp = client.post("/api/holds", json={"showtime_id": showtime_id, "party_size": party_size, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_cancel_then_relock_same_span(client):
    sid = _make_showtime()
    first = _lock(client, sid, 3)
    assert (first["row"], first["start_col"], first["end_col"]) == (1, 1, 3)

    resp = client.post(f"/api/holds/{first['id']}/cancel", json={"reason": "行程有变"})
    assert resp.status_code == 200, resp.text
    cancelled = resp.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_reason"] == "行程有变"
    assert cancelled["cancelled_at"] is not None

    # 取消后原格立即按空闲参与搜索，新锁座重新占到原坐标
    second = _lock(client, sid, 3)
    assert (second["row"], second["start_col"], second["end_col"]) == (1, 1, 3)
    assert second["id"] != first["id"]
    assert second["status"] == "held"


def test_repeat_cancel_fails_with_clear_message(client):
    sid = _make_showtime()
    hold = _lock(client, sid, 2)
    assert client.post(f"/api/holds/{hold['id']}/cancel", json={}).status_code == 200

    resp = client.post(f"/api/holds/{hold['id']}/cancel", json={"reason": "再点一次"})
    assert resp.status_code == 409
    assert "已取消" in resp.json()["detail"]


def test_cancel_missing_hold_returns_404(client):
    resp = client.post("/api/holds/9999/cancel", json={})
    assert resp.status_code == 404
    assert "不存在" in resp.json()["detail"]


def test_cancel_keeps_row_for_reconciliation_and_filter(client):
    sid = _make_showtime()
    hold = _lock(client, sid, 2)
    client.post(f"/api/holds/{hold['id']}/cancel", json={"reason": "用户主动取消"})
    _lock(client, sid, 2)  # 原坐标上的新持座

    # 取消不删行：同一坐标跨度留下取消行 + 新持有行两条记录
    all_holds = client.get("/api/holds").json()
    assert len(all_holds) == 2
    cancelled = [h for h in all_holds if h["status"] == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0]["order_code"] == hold["order_code"]
    assert cancelled[0]["cancel_reason"] == "用户主动取消"
    assert cancelled[0]["cancelled_at"] is not None

    # 列表筛选能区分持有中与已取消
    held = client.get("/api/holds", params={"status": "held"}).json()
    assert [h["status"] for h in held] == ["held"]
    cancelled_only = client.get("/api/holds", params={"status": "cancelled"}).json()
    assert [h["id"] for h in cancelled_only] == [hold["id"]]


def test_seatmap_frees_cells_after_cancel(client):
    sid = _make_showtime()
    hold = _lock(client, sid, 3)

    before = client.get(f"/api/seatmap/{sid}").json()["cells"]
    assert any(c["row"] == 1 and c["col"] == 1 and c["occupied"] and c["heat"] == 1.0 for c in before)

    client.post(f"/api/holds/{hold['id']}/cancel", json={})
    after = client.get(f"/api/seatmap/{sid}").json()["cells"]
    # 热力同步变空：全部座位格均非占用、无占用热力
    assert not any(c["occupied"] for c in after)
    assert all(c["heat"] == 0.0 for c in after if not c["is_aisle"])


def test_released_is_terminal_and_free(client):
    sid = _make_showtime()
    released_id = _insert_hold(
        showtime_id=sid,
        order_code="SB-OLD",
        row=1,
        start_col=1,
        end_col=2,
        party_size=2,
        status=HOLD_STATUS_RELEASED,
    )

    # 已释放的格子按空闲参与搜索索：新锁座可占到同一坐标
    hold = _lock(client, sid, 2)
    assert (hold["row"], hold["start_col"], hold["end_col"]) == (1, 1, 2)

    seatmap = client.get(f"/api/seatmap/{sid}").json()["cells"]
    occupied = {(c["row"], c["col"]) for c in seatmap if c["occupied"]}
    assert occupied == {(1, 1), (1, 2)}  # 只有新持座占用，释放行不产生占用

    # 已释放也是终态：取消它同样失败且提示明确
    resp = client.post(f"/api/holds/{released_id}/cancel", json={})
    assert resp.status_code == 409
    assert "已超时释放" in resp.json()["detail"]

    # 列表筛选能区分已释放
    released = client.get("/api/holds", params={"status": "released"}).json()
    assert [h["id"] for h in released] == [released_id]


def test_list_holds_rejects_unknown_status(client):
    resp = client.get("/api/holds", params={"status": "bogus"})
    assert resp.status_code == 400
    assert "未知状态" in resp.json()["detail"]


def test_partial_unique_index_guards_only_active_spans(client):
    """同一坐标跨度：持有中记录唯一；终态历史行不受限（取消留痕 + 原坐标可再锁）。"""
    from sqlalchemy.exc import IntegrityError

    sid = _make_showtime()
    span = dict(showtime_id=sid, row=2, start_col=3, end_col=4, party_size=2)
    _insert_hold(order_code="SB-A", **span)
    _insert_hold(order_code="SB-B", status="cancelled", **span)  # 终态行可共存
    _insert_hold(order_code="SB-C", status=HOLD_STATUS_RELEASED, **span)

    db = SessionLocal()
    try:
        db.add(SeatHold(order_code="SB-DUP", **span))  # 第二条持有中 → 违反部分唯一索引
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
