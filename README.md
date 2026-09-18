# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座；支持取消持座，取消/超时释放后座位立即回到空闲池。

## 持座状态

| 状态 | 含义 | 是否占座 |
| --- | --- | --- |
| `held` 持有中 | 锁座成功、等待出票 | 是 |
| `cancelled` 已取消 | 用户在持座列表取消，记录原因与时间 | 否（按空闲） |
| `released` 超时释放 | 超时任务释放的终态 | 否（按空闲） |

只有 `held` 占座：列表、座位图热力、锁座/连座搜索三处共用这一「空闲」口径。终态行保留便于对账，同坐标可被新锁座重新占用；终态再次取消返回 `409` 并给出明确提示。

取消接口：`POST /api/holds/{id}/cancel`，请求体 `{"reason": "可选原因"}`。
持座列表支持筛选：`GET /api/holds?status=held|cancelled|released`。


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
3. 订单（持座列表）页查看持座结果，可按持有中/已取消/超时释放筛选；持有中的记录可填写原因后「取消持座」，座位图与连座搜索立即视其为空闲。
4. 冲突页查看重叠请求。

## 开发与测试

```bash
docker compose exec api pytest -q
```
