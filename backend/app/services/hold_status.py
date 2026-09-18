"""持座生命周期状态。

只有 ``held`` 是活跃态、会占座；``cancelled``（用户取消）与
``released``（超时释放）都是终态：行记录保留便于对账，但座位立即视为空闲。
"""

from __future__ import annotations

STATUS_HELD = "held"
STATUS_CANCELLED = "cancelled"
STATUS_RELEASED = "released"

TERMINAL_STATUSES = frozenset({STATUS_CANCELLED, STATUS_RELEASED})

STATUS_LABELS = {
    STATUS_HELD: "持有中",
    STATUS_CANCELLED: "已取消",
    STATUS_RELEASED: "超时释放",
}


def is_held(status: str | None) -> bool:
    return status == STATUS_HELD


def is_terminal(status: str | None) -> bool:
    return status in TERMINAL_STATUSES
