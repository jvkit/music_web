# 06 聚合搜索

`src/music_cli/web/aggregate.py` 实现多音源并发搜索，并对结果去重、排序、可播放验证。

## 入口

```python
async def aggregate_search(
    query,
    media_type="all",
    limit=20,
    timeout=10.0,
    validate_timeout=5.0,
    library=None,
    settings=None,
    get_source_fn=None,
):
    ...
```

## 流程

1. **确定参与源**：读取 `settings.aggregate_sources`，若未配置则使用默认精选源。
2. **并发搜索**：对每个源调用 `search()`。
3. **可播放验证**：对非直连源并发验证 `get_stream_url()` 是否可用。
4. **去重合并**：按规范化后的 `title + artist` 做 MD5 去重。
5. **排序**：按本地已有 > 直连 > 外网 > 不稳定排序。
6. **返回**：截取前 `limit` 条结果。

## 排序规则

```python
def _source_priority(source_name):
    if 本地已有: return 0
    if 直连源: return 1
    if 内置外网源（YouTube/SoundCloud）: return 2
    if 不稳定: return 3
    return 4
```

## 使用场景

聚合搜索适合在首页或搜索页做「全网搜」功能，一次搜索同时查多个平台，给用户最完整的结果。

## 配置

在 `config.json` 中：

```json
{
  "aggregate_sources": ["netease", "bilibili", "web_liumingye", "web_fangpi"],
  "aggregate_validate": true
}
```

## 下一篇

- [SPA 概览与入口](../03_frontend/01_spa_overview.md)
