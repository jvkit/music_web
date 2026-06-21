# 音河（music-cli）完全学习教程

本教程面向希望深入理解并维护「音河」项目的开发者。项目是一个多音源音乐搜索 / 试听 / 下载 CLI + H5 前端，代码量较大，因此按主题拆分成多篇文档，方便按需阅读。

## 阅读建议

1. **先读概览**：了解整体架构与目录结构。
2. **再读后端 / 音源 / 前端**：按自己负责的部分深入。
3. **最后读特性与实战指南**：如分享卡片、一起听、新增音源等。

## 目录

### 00 概览
- [01 项目介绍与整体架构](00_overview/01_intro.md)
- [02 目录结构与文件职责](00_overview/02_directory_structure.md)
- [03 典型数据流：从搜索到播放](00_overview/03_data_flow_search_to_play.md)
- [04 分享卡片端到端流程](00_overview/04_share_end_to_end.md)

### 01 后端核心
- [01 CLI 入口与命令](01_backend/01_cli_and_entry.md)
- [02 配置与设置系统](01_backend/02_config_and_settings.md)
- [03 数据模型](01_backend/03_models.md)
- [04 音乐库 Library](01_backend/04_library.md)
- [05 缓存与本地文件聚合](01_backend/05_cache_and_local.md)
- [06 FastAPI Web 服务概览](01_backend/06_fastapi_overview.md)
- [07 试听、播放与流代理](01_backend/07_preview_and_stream.md)
- [08 下载任务管理](01_backend/08_downloads.md)
- [09 一起听房间](01_backend/09_rooms.md)

### 02 音源体系
- [01 音源架构总览](02_sources/01_source_architecture.md)
- [02 内置原生源](02_sources/02_native_sources.md)
- [03 网页音源适配器](02_sources/03_web_adapter.md)
- [04 音河搜索适配器详解](02_sources/04_liumingye_in_depth.md)
- [05 直连网页音源](02_sources/05_direct_stream_web_sources.md)
- [06 聚合搜索](02_sources/06_aggregate_search.md)

### 03 H5 前端
- [01 前端总览](03_frontend/01_overview.md)
- [02 入口与初始化：app.js 做了什么](03_frontend/02_entry_init.md)
- [03 全局状态、配置与工具函数](03_frontend/03_state_config_utils.md)
- [04 视图与组件](03_frontend/04_components_views.md)
- [05 播放器核心](03_frontend/05_player_core.md)
- [06 播放列表、收藏与批量选择](03_frontend/06_playlists_selection.md)
- [07 一起听歌：房间同步](03_frontend/07_room_together.md)
- [08 密码与安全管理](03_frontend/08_security_password.md)

### 04 核心特性
- [01 分享与 QQ/微信卡片原理](04_features/01_share_cards.md)
- [02 试听、边下边播与下载](04_features/02_preview_stream_download.md)
- [03 一起听歌房间完整流程](04_features/03_rooms_feature.md)
- [04 播放统计与收听频率](04_features/04_playcounts_and_history.md)
- [05 部署架构：nginx + uvicorn + systemd](04_features/05_deployment_architecture.md)

### 05 实战指南
- [01 新增一个网页音源](05_guides/01_add_new_web_source.md)
- [02 常见问题排查](05_guides/02_debug_common_issues.md)
- [03 二次开发与定制](05_guides/03_customize_and_extend.md)

## 约定

- 所有路径均相对于项目根目录 `/home/ubuntu/workspace/music`。
- 代码片段来自实际源码，随项目迭代可能略有变化，建议结合当前源码阅读。
- 若发现文档与代码不一致，优先以代码为准，并可在 `knowledge/` 中记录偏差。
