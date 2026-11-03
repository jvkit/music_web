# 网易云音乐公开接口侦察记录（发现页 / 推荐 / 识曲）

日期：2026-11-03。背景：为 Web 端「发现」可逛页面 + 推荐系统选型，实测网易云音乐
哪些公开接口可免登录直调。结论先行：**发现页所需接口全部可用，推荐三件套（相似歌曲 /
含此歌的歌单 / 私人FM）也全部免登录可用；听歌识曲是 eapi 加密接口，curl 打不通，需移植
weapi/eapi 加密后可用（二期）**。

## 通用约定

- BASE：`https://music.163.com`，全部为明文 `/api/...` GET/POST。
- 必带请求头：`User-Agent: Mozilla/5.0...` + `Referer: https://music.163.com/`。
- **免登录、免 Cookie**，返回 JSON 内层 `code == 200` 为成功。
- 前端**不可直连**（CORS 拦截），必须由后端代理转发（走 FastAPI 新增 discover router）。
- 国内直连即可，**不要挂代理**（proxy 只用于 youtube/soundcloud）。

## 已验证可用（2026-11-03 实测通过）

| 用途 | 端点 | 关键参数 | 实测结果 |
|---|---|---|---|
| 官方榜单列表 | `GET /api/toplist/detail` | - | 返回全部榜单（热歌榜/新歌榜/飙升榜…）名称+封面+id |
| 歌单详情（含曲目） | `GET /api/playlist/detail` | `id=3778678` | 热歌榜一次返回 **200 首完整元数据**（name/artists/album/duration/id） |
| 分类歌单墙 | `GET /api/playlist/list` | `cat=摇滚&offset=0&limit=30` | 按分类返回歌单卡片（名称/播放量/封面） |
| 精品歌单 | `GET /api/playlist/highquality/list` | `cat=全部&limit=` | 高质量歌单墙，封面精美 |
| 相似歌曲 | `GET /api/v1/discovery/simiSong` | `songid=347230` | 5 首相似歌（推荐核心） |
| 含此歌的歌单 | `GET /api/discovery/simiPlaylist` | `songid=347230` | 含这首歌的歌单（推荐核心） |
| 推荐歌单（免登录） | `GET /api/personalized/playlist` | `limit=` | 通用推荐歌单（非个性化，无需登录） |
| 推荐新歌（免登录） | `GET /api/personalized/newsong` | `limit=` | 通用推荐新歌 |
| 新碟上架 | `GET /api/album/new` | `area=ZH&limit=` | 新专辑列表 |
| 歌手热门歌曲 | `GET /api/artist/{id}` | - | 歌手信息 + hotSongs |
| 歌曲详情 | `GET /api/song/detail` | `ids=[347230]`（JSON 数组字符串） | 单曲元数据 |
| 私人 FM | `GET /api/v1/radio/get` | - | **免登录也能通**，每次调用返回随机推荐曲（含完整 id/歌手） |

曲目字段映射（playlist/detail 的 tracks[i]）：`id` → `netease:{id}`（现有 Track 格式，
`preview`/`play_resolve` 直接可放）；`name`、`artists[].name`、`album.name`、
`album.picUrl`（封面，可走 `/api/thumbnail` 代理防盗链）、`duration`（毫秒）。

## 实测不可用（明文 /api 通道）

- `playlist/catalog/detailed`、`playlist/catlist`（分类目录树）→ 404。**分类列表改为后端
  硬编码**（网易云分类体系稳定：华语/流行/摇滚/民谣/电子/说唱/ACG/影视原声/清晨/深夜/
  学习/运动…挑常用的十几个即可），`playlist/list?cat=` 接受任意分类名。
- `simiSong`(旧)、`simiArtist` → 404；`artist/similar` → 400（需 eapi）。
- `top/song`（新歌速递）→ 404（需 eapi），用 `personalized/newsong` 替代。
- `search/suggest`（搜索建议）→ 400（weapi 专用）。搜索建议改用自家曲库前缀匹配即可。
- `POST /api/music/audioMatch`（**听歌识曲**）→ 404：走 eapi 加密通道。可行性：参考
  NeteaseCloudMusicApi 项目的 `search` 识曲实现（`/eapi/music/audioMatch`，需 weapi/eapi
  加密 + 音频指纹参数），纯 Python 可移植加密层，工作量中等，列为二期。

## 缓存与频控建议（后端代理实现时）

- 榜单列表 / 分类歌单墙：TTL 1 小时；歌单详情：TTL 24 小时（榜单内曲目随榜单刷新）。
- 私人 FM / 相似歌曲：不缓存（本来就是随机/即时）。
- 缓存独立放内存 dict 即可（几个朋友用，量极小）；**绝不写入 library.json**。

## 推荐系统结论

免登录版「猜你喜欢」= `simiSong`（单曲种子）+ `simiPlaylist`（歌单种子）+ `radio/get`
（FM 随机流）组合，种子可来自自家 `server_library`（收藏/播放记录），播放兜底全走现有
`play_resolve` 换源链。无需任何自有曲库数据。
