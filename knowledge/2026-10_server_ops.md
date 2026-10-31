# 服务器部署与运维经验（2026-10-31）

线上 jvkit.cn（腾讯云轻量，82.157.178.112，ssh 别名 `j`）部署本服务的踩坑全记录。

## 部署流水线（标准流程）

```bash
# 本地
git push origin fix/source-rescue:main
# 服务器
cd /home/ubuntu/workspace/music && git pull origin main
env UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple /home/ubuntu/.local/bin/uv sync
sudo systemctl restart music-web.service
```

### 必踩的坑

- **`uv sync` 不会自动重装同名版本的本地包**：push 新代码后 `uv run` 可能继续用 venv 里的旧
  yinhe（0.2.0）。必须显式跑 `uv sync`，且 ssh 非交互 shell 里 `uv` 不在 PATH，要用绝对路径
  `/home/ubuntu/.local/bin/uv`。
- **PyPI 官方源在服务器极慢会卡死 uv sync**：必须 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`。
- **systemd 单元 ExecStart 过期**：历史上是 `music serve`（CLI 时代），已改为
  `uv run music-web --host 0.0.0.0 --port 8001`（/etc/systemd/system/music-web.service）。
- **僵尸 uvicorn 占 8001**：旧 `uv run uvicorn music_cli.web.main:app` 进程可能残留并占住
  8001，systemd 新服务看似 active 实则没绑定成功。用 `sudo ss -tlnp | grep 8001` 确认监听者。
- **部署后验证单**：本地 curl `127.0.0.1:8001/api/me` 应 401（路由在线），`/api/library` 200；
  线上再验证 `https://jvkit.cn/music/api/...` 一遍（nginx 反代 /music/ → 8001，root_path 不影响直连）。

## 服务自带的 mihomo 代理（/home/ubuntu/mihomo-proxy）

用户给的 SakuraCat Linux AppImage 链接（file-cdn.cat-cdn.com）**CDN 域名已死**。
实际方案 = mihomo 官方内核 + 本地 SakuraCat 的 runtime.yaml（登录后拉取的完整节点配置）。

- 内核：MetaCubeX/mihomo releases，`mihomo-linux-amd64-compatible-vX.Y.Z.gz`。
  GitHub 匿名 API 限流（代理 IP 共享限额），用 `gh` CLI + `https_proxy` 环境变量下载。
- systemd 托管：`mihomo -d /home/ubuntu/mihomo-proxy`（config.yaml = runtime.yaml 副本，
  mixed-port 7890，external-controller 127.0.0.1:9090）。
- **MMDB 卡死**：mihomo 首次启动要下载 geoip.metadb，服务器下载不动会卡住。
  解法：把本地 SakuraCat 目录（`%APPDATA%/com.core.SakuraCat`）的 `geoip.metadb`、
  `geosite.dat` 直接传到工作目录。
- **节点组切换**：RESTful API（127.0.0.1:9090）：
  `GET /proxies` 看组；`/proxies/<组>/delay?timeout=4000&url=<gstatic204>` 测延迟；
  `PUT /proxies/<组>` body `{"name": "<节点>"}` 切换。组嵌套：节点选择→自动节点→具体节点。
  「自动节点」默认选的节点可能已死，延迟测试选最快的切过去。
- **DNS 000 问题（已解决，2026-10-31）**：症状是流量日志显示 `match ... using 节点` 但 curl 仍 000。
  实际**没有改任何配置**——重启服务后 url-test 重新测速换到可用节点，出口即通
  （google/youtube/soundcloud 全 200）。教训：Sakura 的 fallback DoH（1.1.1.1 等）在国内
  确实不可达，但 mihomo 并行查询多 nameserver（doh.pub/alidns 可达），域名解析不受影响；
  000 时先等 url-test 跑完一轮或 `PUT /proxies/节点选择 {"name":"自动节点"}` 让它自动换点，
  别急着改 DNS 段。
- **节点自动切换（已配置）**：`节点选择` 组已切到 `自动节点`（url-test 全量节点组），
  节点挂了自动选最快，无需人工。
- **看门狗（已配置）**：`/home/ubuntu/mihomo-proxy/watchdog.sh` + systemd
  `mihomo-watchdog.timer`（每 5 分钟）：curl google+youtube 经代理探测，不通则先调 API
  让 url-test 组重新测速（`/group/自动节点/delay?timeout=5000&url=http://www.gstatic.com/generate_204`），
  仍不通重启 mihomo-proxy，日志 `watchdog.log`。注意 API 路径里的组名要 URL encode
  （python urllib.parse.quote）。
- **music 服务接代理（已配置）**：`~/.config/music/config.json` 写
  `{"proxy": "http://127.0.0.1:7890"}`，`systemctl restart music-web` 生效。
  ⚠️ settings.py 注释写 `~/.config/musiic-cli/config.json` 是错的：platformdirs 在 Linux 忽略
  appauthor，实际路径是 `~/.config/music/`（该目录还有 announcement.json/users.json 可作旁证）。
  线上已验证：`/api/search?source=youtube|soundcloud` 返回真实结果 200。

### ssh 反向转发

ssh config `Host j` 原有的 `RemoteForward 17890 localhost:7890`（借本地代理）**已注释停用**——
服务器自跑 mihomo 后不再需要，留着反而会因本地代理没开导致 ssh 建连异常。

## 代码层的教训

- **WS 路由里用未定义变量 = 握手 500**：im_api.py 第一版用了 `logger.info` 但漏了
  `logger = logging.getLogger(__name__)`，所有 WS 握手 NameError → 客户端收到
  "Expected HTTP 101 but was 500"。症状（101 变 500）先查服务端日志的 Traceback，
  别怀疑 token/头/URL。
- **分源代理**（deps.py）：`_PROXY_SOURCES = {"youtube", "soundcloud"}`，get_web_source 只有
  命中才取 settings.proxy，其余传 None 直连。验证手法：把 settings.json proxy 改成死端口，
  国内源应仍 200、外网源才超时。

## 下载页与公告

- 下载页：`/home/ubuntu/www/download/music/`（nginx 已配 /download/music/ 路由，index.html
  自带"检测 /download/music/app 存在即放行下载"逻辑）。apk 放 `app/yinhe-music.apk`，
  直链 `https://jvkit.cn/download/music/app/yinhe-music.apk`。
- 公告：`GET /api/announcement` 读 `config/announcement.json`（改内容免重启；注意真实
  config 目录是 `/home/ubuntu/.config/music/`，不是项目根 config/）。App 每次启动弹一次。
