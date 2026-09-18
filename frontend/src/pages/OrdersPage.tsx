import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { holdStatusLabel } from "../status";

type Hold = {
  id: number;
  showtime_id: number;
  order_code: string;
  row: number;
  start_col: number;
  end_col: number;
  party_size: number;
  status: string;
  cancel_reason: string | null;
  cancelled_at: string | null;
  created_at: string;
};

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "held", label: "持有中" },
  { value: "cancelled", label: "已取消" },
  { value: "released", label: "已释放" },
];

export default function OrdersPage() {
  const [rows, setRows] = useState<Hold[]>([]);
  const [filter, setFilter] = useState("");
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    const qs = filter ? `?status=${filter}` : "";
    api<Hold[]>(`/holds${qs}`)
      .then(setRows)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [filter]);

  useEffect(load, [load]);

  async function confirmCancel(id: number) {
    setMsg("");
    setErr("");
    try {
      const body = reason.trim() ? { reason: reason.trim() } : {};
      const hold = await api<Hold>(`/holds/${id}/cancel`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setMsg(`已取消 ${hold.order_code}，原座位已释放为空闲`);
      setCancellingId(null);
      setReason("");
      load();
    } catch (e) {
      // 重复取消等终态冲突在此给出后端明确提示
      setErr(e instanceof Error ? e.message : String(e));
      setCancellingId(null);
      load();
    }
  }

  return (
    <>
      <h2>订单</h2>
      <div className="toolbar">
        <label>
          状态{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            {FILTERS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </label>
        <button onClick={load}>刷新</button>
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
            <th>取消信息</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((h) => (
            <tr key={h.id}>
              <td className="mono">{h.order_code}</td>
              <td>{h.showtime_id}</td>
              <td className="mono">
                R{h.row} C{h.start_col}-{h.end_col}
              </td>
              <td>{h.party_size}</td>
              <td>
                <span className={`badge badge-${h.status}`}>{holdStatusLabel(h.status)}</span>
              </td>
              <td className="mono">
                {h.status === "cancelled" ? (
                  <>
                    {h.cancel_reason || "—"}
                    {h.cancelled_at && (
                      <div className="cancel-meta">{new Date(h.cancelled_at).toLocaleString()}</div>
                    )}
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td>
                {h.status === "held" &&
                  (cancellingId === h.id ? (
                    <span className="cancel-editor">
                      <input
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="取消原因（可选）"
                      />
                      <button onClick={() => confirmCancel(h.id)}>确认取消</button>
                      <button
                        className="btn-ghost"
                        onClick={() => {
                          setCancellingId(null);
                          setReason("");
                        }}
                      >
                        放弃
                      </button>
                    </span>
                  ) : (
                    <button
                      className="btn-ghost"
                      onClick={() => {
                        setCancellingId(h.id);
                        setReason("");
                        setMsg("");
                        setErr("");
                      }}
                    >
                      取消
                    </button>
                  ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
