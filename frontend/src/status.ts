/** 持座状态：held 为唯一活跃态；cancelled / released 均为终态（格子按空闲处理）。 */
export const HOLD_STATUS_LABELS: Record<string, string> = {
  held: "持有中",
  cancelled: "已取消",
  released: "已释放",
};

export function holdStatusLabel(status: string): string {
  return HOLD_STATUS_LABELS[status] ?? status;
}
