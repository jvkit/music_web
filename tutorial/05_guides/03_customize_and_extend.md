# 05-03 二次开发与定制

学会项目结构和代码位置后，你可以做很多定制。这一篇列出最常见的修改点。

## 1. 修改管理密码

编辑 `src/web/static/js/passwordGate.js`：

```js
const ADMIN_PASSWORD = 'jvkit123';
```

改成你自己的密码。注意：这只是前端密码，懂技术的人可以在浏览器里看到。如果要求真正的安全，需要后端也加校验。

## 2. 修改站点标题和主题色

- 标题：`src/web/static/index.html` 里的 `<title>` 和 `app.js` 里的 `document.title`。
- 主题色：`index.html` 里的 `data-theme="dim"`，可以改成 DaisyUI 支持的其他主题，如 `dark`、`light`、`cupcake`。
- Logo/品牌色：改 `index.html` 里的渐变类和 `styles.css`。

## 3. 给前端增加新的设置项

以「默认搜索分页数」为例，步骤：

1. `src/web/static/js/config.js` 的 `DEFAULT_SETTINGS` 加字段。
2. `src/web/static/index.html` 加对应的 input/select。
3. `src/web/static/js/dom.js` 的 `cacheElements` 里加 id。
4. `src/web/static/js/views/settings.js` 里读写该字段。
5. 保存时调用 `requireAdminPassword`。

如果设置需要影响后端，再加一个 API 接口或环境变量。

## 4. 修改前端音源分组

编辑 `src/web/static/js/app.js` 的 `SOURCE_GROUPS`：

```js
{
    id: 'custom',
    name: '我的收藏源',
    sources: ['web_example', 'netease']
}
```

不需要改后端，刷新页面即可生效。

## 5. 隐藏某个音源

如果某个源不稳定但不想删代码，可以在 `src/music_cli/settings.py` 的 `Settings` 里把它加入 `hidden_sources`：

```python
hidden_sources: list[str] = Field(default_factory=lambda: ["qqmp3"])
```

前端下拉框会隐藏它，但已下载的本地文件仍可播放。

## 6. 修改分享卡片尺寸/质量

编辑 `src/music_cli/web/api.py` 的 `_build_share_meta`：

```python
if is_wechat and query_key == "c" and query_value:
    image_url = f"{base}api/share_image?code={query_value}&w=300&h=300&q=30"
```

改 `w`、`h`、`q` 可以调整微信分享图的大小和压缩率。

## 7. 增加后端 API 接口

在 `src/music_cli/web/api.py` 里：

```python
class MyRequest(BaseModel):
    name: str

@app.post("/api/my_feature")
def api_my_feature(req: MyRequest):
    return {"hello": req.name}
```

然后在 `src/web/static/js/api.js` 加封装：

```js
export async function myFeature(name) {
    const response = await apiFetch('/my_feature', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
    return response.json();
}
```

## 8. 修改部署路径

如果想从 `/music/` 改成 `/app/music/`：

1. nginx location 改成 `/app/music/`。
2. nginx 里的 `X-Forwarded-Prefix` 改成 `/app/music`。
3. `music serve` 的 `--root-path` 改成 `/app/music`。
4. 前端代码里用的是相对路径 `api`，不需要改。

## 9. 开启入站密码

`index.html` 里入站密码的 HTML 被注释掉了。取消注释：

```html
<div id="passwordGate" class="fixed inset-0 ...">
    ...
</div>
```

然后改 `passwordGate.js` 里的 `SITE_PASSWORD`。

## 10. 自定义首页空状态

搜索为空时的提示在 `src/web/static/js/views/search.js`：

```js
container.insertAdjacentHTML('beforeend', '<div class="py-12 text-center ...">暂无搜索结果</div>');
```

可以改成更友好的引导文案或动画。

## 11. 加日志

后端用 Python 标准 `logging`：

```python
import logging
logger = logging.getLogger(__name__)

logger.info("搜索完成: %s", query)
logger.warning("流地址获取失败: %s", e)
```

前端用 `console.log`/`console.error`，但生产环境尽量少打。

## 12. 单元测试

虽然项目目前没有完整测试，但你可以按功能模块加：

```bash
mkdir -p tests/sources
```

例如测试一个网页音源的搜索：

```python
from music_cli.sources.web.sites.group_a.gequbao import adapter

def test_gequbao_search():
    src = adapter()
    tracks = src.search("周杰伦", limit=5)
    assert len(tracks) > 0
    assert tracks[0].title
```

运行：

```bash
uv run pytest tests/
```

## 修改后记得做三件事

1. **重启后端**：Python 代码修改后必须重启 uvicorn。
2. **硬刷新前端**：按 `Ctrl+Shift+R` 或清缓存，避免浏览器用旧 JS/CSS。
3. **测试相关功能**：改一个模块后，把上下游功能都点一遍。

## 小结

Musiic 的代码结构比较清晰，二次开发主要改这几个地方：

- 前端界面：`index.html`、`styles.css`、`js/` 对应视图。
- 前端逻辑：`app.js`、`state.js`、`config.js`、各视图文件。
- 后端接口：`src/music_cli/web/api.py`。
- 音源适配：`src/music_cli/sources/web/sites/`。
- 部署配置：nginx + systemd + `music serve` 参数。

教程到这里就结束了。建议你先通读一遍，再挑最感兴趣的模块深入看源码。
