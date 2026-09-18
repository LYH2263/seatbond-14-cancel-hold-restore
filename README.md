# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |
| API 文档 | http://localhost:9100/docs |
| Postgres | localhost:5442 |

健康检查：`GET http://localhost:9100/api/health`

## 页面

- `/halls` — 影厅
- `/showtimes` — 场次
- `/seatmap` — 座位图（大网格热力）
- `/hold` — 锁座
- `/orders` — 订单
- `/conflicts` — 冲突

## 使用说明

1. 在影厅与场次页确认厅图与排期。
2. 打开座位图查看占用热力，在锁座页输入连座人数并提交。
3. 订单页查看持座结果；冲突页查看重叠请求。

## 取消持座与状态语义

持座有三种状态，列表可按状态筛选：

| 状态 | 含义 | 占座 |
| --- | --- | --- |
| `held` 持有中 | 唯一活跃态，可取消 | 是 |
| `cancelled` 已取消 | 终态，行记录与取消原因保留用于对账 | 否 |
| `released` 已释放 | 终态（超时释放），同样保留记录 | 否 |

- 取消：`POST /api/holds/{id}/cancel`，请求体 `{"reason": "可选取消原因"}`。
  仅 `held` 可取消；对已取消/已释放再次取消返回 `409` 及明确提示。
- 座位图、自动连座搜索、冲突检测只认 `held`：取消或释放后，原坐标立即按空闲参与搜索，可被新锁座重新占到。
- 列表筛选：`GET /api/holds?status=held|cancelled|released`。
- 取消不删行：同一坐标跨度会留下取消行与新持座行两条记录，便于对账。
  数据库层以部分唯一索引 `uq_hold_span_active` 保证同一坐标跨度最多一条持有中记录。

## 开发与测试

```bash
docker compose exec api pytest -q
```

本地无 Docker 时，后端测试使用内存 SQLite，无需 Postgres：

```bash
cd backend && python3 -m pytest -q
```
