# 超级聚合搜索设计文档

> 状态：设计稿，暂缓实现  
> 创建时间：2026-06-15

## 1. 目标

提供一个统一的搜索入口，并发查询所有可用音源，对结果去重合并后返回，并暴露 REST API 供 H5 / 小程序 / 外部程序调用。

## 2. 非目标

- 不替代现有单源搜索 `/api/search`。
- 不实现跨源歌词/封面补齐（仅合并已有元数据）。
- 不涉及付费/登录态的源调度策略。

## 3. 设计决策

| 决策项 | 选型 | 说明 |
| --- | --- | --- |
| 查询范围 | 所有可用源（约 13 个） | 包括 youtube、netease、bilibili、soundcloud 及网页适配器可用站点。 |
| API 鉴权 | 无 | 内网 / H5 自用，复用现有 FastAPI CORS 配置。 |
| 去重策略 | 严格去重 | 按「规范化标题 + 规范化艺术家」合并同一首歌。 |
| 失败处理 | 快速满足 + 失败明细 | 不等待全部源；失败源写入 `errors` 字段。 |
| 翻页 | `offset` + 短时缓存 | 首屏 20 条，点击更多时通过缓存切片返回，避免重复搜源。 |

## 4. API 设计

### 4.1 端点

```http
GET /api/search/aggregate?q={keyword}&media_type=all&limit=20&offset=0&timeout=10
```

参数：

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `q` | string | 必填 | 搜索关键词 |
| `media_type` | string | `all` | `audio` / `video` / `all` |
| `limit` | int | `20` | 本次返回条数，最大 `100` |
| `offset` | int | `0` | 翻页偏移 |
| `timeout` | int | `10` | 每源超时（秒），全局硬超时为 `timeout + 2` |

### 4.2 响应示例

```json
{
  "query": "晴天",
  "media_type": "all",
  "total": 47,
  "returned": 20,
  "offset": 0,
  "limit": 20,
  "results": [
    {
      "id": "a1b2c3d4",
      "title": "晴天",
      "artist": "周杰伦",
      "duration": 269,
      "cover_url": "https://...",
      "sources": [
        {
          "source": "netease",
          "track_id": "186016",
          "source_url": "https://music.163.com/#/song?id=186016",
          "media_type": "audio",
          "quality": "standard"
        },
        {
          "source": "qqmp3",
          "track_id": "xxx",
          "source_url": "...",
          "media_type": "audio"
        }
      ]
    }
  ],
  "errors": {
    "musicenc": "timeout",
    "yinyueke": "unavailable"
  }
}
```

## 5. 核心流程

```
接收请求
  │
  ▼
并发启动所有可用源搜索任务
  │
  ▼
每源独立超时（asyncio.gather(return_exceptions=True)）
  │
  ▼
规范化 title/artist → 生成去重 key
  │
  ▼
合并相同 key 的结果，保留多个 source 选项
  │
  ▼
达到 limit 条唯一结果 或 全局超时
  │
  ▼
按源优先级/质量排序后返回
```

## 6. 去重规则

- 标题规范化：转小写、去除 `()[]{}` 等标点、合并连续空白。
- 艺术家规范化：同上；多个艺术家按 `&` / `,` / `/` 拆分后排序再拼接。
- 去重 key：`sha256(norm_title + "||" + norm_artist)`。
- 同一 key 下保留多个 `source` 条目，便于播放时择优。

## 7. 性能与容量评估

- **4 核 4G 服务器**：足够。十几个并发 HTTP 请求为 I/O 密集型，CPU 占用极低；去重/规范化计算量可忽略。
- **真正瓶颈**：外部源响应延迟、限频、偶发不可用。
- **建议防护**：
  - 每源独立超时，避免单源拖垮整体。
  - 单 IP / 单会话请求限流（如 10 req/min）。
  - 短时缓存（60s TTL）减少重复查询对上游的压力。

## 8. 实现建议

### 8.1 新增文件

- `src/music_cli/search/aggregate.py`：聚合搜索核心实现。
- `src/music_cli/search/dedup.py`：规范化与去重逻辑。
- `src/music_cli/search/cache.py`：短时结果缓存（可先用内存 dict，后续换 Redis）。

### 8.2 API 层改动

在 `src/music_cli/web/api.py` 新增：

```python
@app.get("/api/search/aggregate")
async def aggregate_search(...):
    ...
```

### 8.3 与现有代码的关系

- 复用 `music_cli.sources.get_source()` 和 `Source.search()`。
- 复用 `music_cli.models.Track` 作为源内结果结构。
- 返回结构新增 `AggregateTrack`，与 `Track` 不完全相同（包含多 source 选项）。

## 9. 风险

- 外部源大量并发可能被限频或封 IP。
- 不稳定源拖慢响应时，虽然做了超时，但失败率可能偏高。
- 严格去重可能把「原版」和「live 版」误判为同一首。

## 10. 后续可考虑增强

- 支持 `sources` 参数，让调用方指定只查某些源。
- 基于历史成功率动态调整源优先级。
- 接入 Redis 缓存，支持多进程共享。
- 增加搜索结果的热度/相关度排序。
