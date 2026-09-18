import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";

type Hold = {
  id: number;
  showtime_id: number;
  order_code: string;
  row: number;
  start_col: number;
  end_col: number;
  party_size: number;
  status: string;
  status_label: string;
  cancel_reason: string | null;
  cancelled_at: string | null;
  created_at: string | null;
};

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "held", label: "持有中" },
  { value: "cancelled", label: "已取消" },
  { value: "released", label: "超时释放" },
];

export default function OrdersPage() {
  const [rows, setRows] = useState<Hold[]>([]);
  const [filter, setFilter] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [reasonFor, setReasonFor] = useState<Record<number, string>>({});

  const load = useCallback(() => {
    const qs = filter ? `?status=${encodeURIComponent(filter)}` : "";
    api<Hold[]>(`/holds${qs}`).then(setRows);
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  async function cancel(h: Hold) {
    setMsg("");
    setErr("");
    setBusyId(h.id);
    try {
      const reason = (reasonFor[h.id] ?? "").trim();
      const out = await api<Hold>(`/holds/${h.id}/cancel`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setMsg(`已取消 ${out.order_code}：第${out.row}排 ${out.start_col}-${out.end_col} 已释放`);
      setReasonFor((m) => ({ ...m, [h.id]: "" }));
      load(); // 刷新后持有中与已取消可区分，座位图/搜索亦视该格空闲
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <>
      <h2>持座列表</h2>
      <div className="toolbar">
        {FILTERS.map((f) => (
          <button
            key={f.value || "all"}
            onClick={() => setFilter(f.value)}
            style={
              filter === f.value
                ? { background: "var(--cinema-warm)", color: "#1a1200" }
                : { background: "#2a1a22", color: "var(--text)", border: "1px solid #4a3040" }
            }
          >
            {f.label}
          </button>
        ))}
        <button onClick={load} style={{ background: "#2a1a22", color: "var(--text)", border: "1px solid #4a3040" }}>
          刷新
        </button>
      </div>
      {msg && <div className="ok">{msg}</div>}
      {err && <div className="err">{err}</div>}
      <table className="table">
        <thead>
          <tr>
            <th>订单号</th>
            <th>场次</th>
            <th>座位</th>
            <th>人数</th>
            <th>状态</th>
            <th>取消原因</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.id} className={h.status === "held" ? "" : "row-terminal"}>
              <td className="mono">{h.order_code}</td>
              <td>{h.showtime_id}</td>
              <td className="mono">
                R{h.row} C{h.start_col}-{h.end_col}
              </td>
              <td>{h.party_size}</td>
              <td>
                <span className={`badge badge-${h.status}`}>{h.status_label}</span>
              </td>
              <td className="cell-reason">{h.cancel_reason || "—"}</td>
              <td>
                {h.status === "held" ? (
                  <div className="cancel-cell">
                    <input
                      value={reasonFor[h.id] ?? ""}
                      onChange={(e) => setReasonFor((m) => ({ ...m, [h.id]: e.target.value }))}
                      placeholder="取消原因（可选）"
                      style={{ width: 160 }}
                    />
                    <button
                      onClick={() => cancel(h)}
                      disabled={busyId === h.id}
                      style={{ background: "var(--cinema-warm)" }}
                    >
                      {busyId === h.id ? "取消中…" : "取消持座"}
                    </button>
                  </div>
                ) : (
                  <span className="stub-empty">终态不可操作</span>
                )}
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={7} className="stub-empty">
                暂无记录
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
