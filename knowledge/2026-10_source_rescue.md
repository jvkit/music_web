# 音源抢救记录（2026-10-31）

对全部 13 个音源做了存活探测（直连 + 代理对比），结论与处置如下。

## 存活矩阵

| 音源 | 搜索 | 试听 | 处置 |
|------|------|------|------|
| netease（内置） | ✅ | ✅ | 主力源；VIP/版权曲返回空链是上游限制 |
| bilibili（内置） | ✅ | 视频源 | App 音频场景用不上；网页端自用 |
| youtube / soundcloud | ❌ | - | 服务器出网受限，配代理即可活（settings.json `proxy`），暂不处理 |
| web_tonzhon 铜钟 | ✅ | ✅ | 正常 |
| web_qqmp3 | ✅ | ✅ | 正常（仍标 unstable，被关键词拦截时会空） |
| web_liumingye 音河搜索 | ✅ | ✅ | 正常，meting 聚合，版权覆盖最好 |
| web_gequbao 歌曲宝 | ✅ | ✅ | 已修复：play-url 需 `purpose=play`；Cloudflare 挡 requests TLS，改用 curl_cffi |
| web_fangpi 放屁网 | ✅ | ✅ | 已修复：站点搬家 `fangpi.net → fangpiw.com`（301），其余同歌曲宝 |
| web_jbsou JB搜 | ✅ | ✅ | 已修复：X-Mk-Guard WAF 需先取首页 `mk_visit` 令牌（内联脚本签发，12h 有效） |
| web_netease_fe_mm | ✅ | ❌ | `/song/url` 对全量歌曲返回 null；标记 unstable，价值低（网易系已有主力源） |
| web_musicenc | ❌ | - | 站点全球性死亡（直连/代理双超时），已注销注册 |
| web_tonzhon_whamon | ❌ | - | 镜像域名 DNS 不存在，已注销注册 |

## 关键经验

- **Cloudflare TLS 指纹封锁**：gequbao、fangpiw 对 python-requests 一律 403（Server: cloudflare），
  curl/wget 能过。解法是 `curl_cffi.Session(impersonate="chrome124")`，API 与 requests 兼容。
- **X-Mk-Guard（煎饼搜）**：不是 TLS 指纹，是令牌校验——首页 HTML 内联脚本
  `document.cookie="mk_visit=<epoch>-<hex>"`，带 Cookie 请求即放行，403 时刷新令牌重试。
- **同族站点批量变更**：gequbao/fangpi 同属一套模板（相同 class 名、相同 member/common-play-url），
  API 变更是同步的，修一个要检查另一个。
- 探测外部站点可用性时，「本机直连」最接近服务器网络环境；「代理通但直连不通」即归外网源。

## 重新注册死源的方法

`src/yinhe/sources/web/__init__.py` 的 `_load_adapters()` 里把 import 和模块列表加回来即可，
站点文件仍保留在 `sites/group_a|b/` 下。
