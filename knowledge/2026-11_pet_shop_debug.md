# 宠物动作商店 & 素材下载排查实录（2026-11-02）

客户端 `andr` 关于宠物系统的三个连锁问题，以及排查过程中的错误方向。**都是"看起来像 UI/素材问题、
实际是状态管理或权限边界"的典型**。

---

## 一、动作货架恒空 / 商店"未上架"

### 现象
- 动作页所有动作显示"未上架"，一个都买不了
- 鲸鱼娘的动作货架完全为空，怎么升级都没货
- 图鉴只有 6 个动作，但素材明明有 15 段

### 根因（三个独立 bug 叠加）

**① species → character 映射漏做**
`_starter_actions()` 里把 `default` 映射成 `boy`，但 `_shelf_for()` 漏了这一步：

```python
species = pet.get("species") or "default"      # "default"
pool = [a for a in catalog if a.get("character") == species]   # 等于 "default"，永远命中不了
```

actions 目录里 `character` 写的是 `boy`，所以候选池恒为空。

**② 空货架被永久缓存**
即使修好①，之前生成的 `shop_shelves: {"1": []}` 已经落库。原逻辑 `if key in shelves: return`
把空数组当有效缓存，永远不会重新生成。改为判空：

```python
if shelves.get(key):   # 而不是 if key in shelves
    return shelves[key]
```

**③ starter 加了也不补发**
`_ensure_pet_schema()` 原来只在 `action_unlocks` **缺 key** 时写 starter。
manifest 后来扩充了 starter 动作，老 pair 的 key 已存在，永远不会更新 → 图鉴卡在旧集合。

### 还要注意
货架 key 必须是 `"{character}:{level}"`。只按 `"{level}"` 存的话，切换物种后
鲸鱼娘会复用大肥鱼的货架，显示一堆对不上角色的动作。

---

## 二、"未上架"其实是货架机制和全量列表打架

`/pet/shop` 最初只返回 `shelf`（随机 4~6 个折扣动作）。客户端后来改成"全量列表"展示，
但货架外的动作没有价格，只能显示"未上架"。

**正解**：`/pet/shop` 同时返回 `catalog`——该角色全部动作，每项带
`unlocked / locked_by_level / on_shelf / price`。货架内走折扣价，货架外走标准价
`ACTION_BASE_PRICE + (min_level-1)*5`。`buy_action` 也相应放开为货架内外都能买。

这样货架退化成"随机折扣"这一层运营手段，不再承担"能不能买"的闸门职责。

---

## 三、角色疯狂在 boy 和鲸鱼娘之间交替 + 反复大量下载

### 现象
进精灵中心后角色反复闪切，同时后台一直下载素材（几十 MB 反复拉）。

### 根因：Compose state 驱动的死循环

```
refresh() 无条件改 characters (Compose state)
  → PetAvatar 的 characterId = characterIdFor(species) 重新计算
  → remember(characterId, character, unlockedActions) 键变化 → 动画引擎销毁重建
  → LaunchedEffect(characterId) 重新触发 → 又调 refresh()
  → 回到第一步
```

同时 `refresh()` 里 `PetFrameCache.clear()` + `readyActs.clear()` 让帧暂时取不到，
`decodeFrame` 回退到 assets 里的 boy → 视觉上就是"boy 和鲸鱼娘交替"。
引擎每重建一次就当作没下载过 → 重新拉一遍素材。

**一个更隐蔽的放大器**：早期代码比较的是对象相等
`if (map != characters)`，而清单里的 boy 会被替换成内置 `BOY` 对象，
下轮拉到的又是服务端版本，**永远不相等**，于是每轮都赋值。

### 修复要点
1. `refreshMutex` + `refreshing` 标志，串行化并发调用
2. **只在 `manifest.version` 变化时替换 `characters`**，版本相同直接 return
3. 版本没变时不清 `readyActs` / `PetFrameCache`
4. 首次加载从 SharedPreferences **恢复**已解压记录，而不是清空后重下

> 经验：Compose 里凡是"某 state 派生 → 派生值做 remember key → 副作用再改该 state"的链路，
> 都要检查会不会自激。比较对象相等基本不可靠，用版本号/时间戳这类单调量。

---

## 四、未购买的动作为什么会被播、被下载（权限漏洞）

`PetAnimationEngine.allowed()` 原实现：

```kotlin
return name in roles.idle || name in roles.music || name in roles.click ||
    name in roles.sleepStart || ... || roles.events.values.any { name in it }
```

**只要 clip 被写进 roles 任意槽位就放行**。而大肥鱼的 `roles.move` 含 `windbounce`、
`原地左转奔跑`，`roles.turn` 含 `东张西望`——这三个都在商店里卖。
于是随机池会抽中它们，`PetAvatar` 的按需下载逻辑又会让它去拉对应 pack。

修复：引擎构造时传入 `sellable`（该角色在售 clip 集合），未购买的即使被 roles 引用也拒绝。

```kotlin
if (name in starter || name in unlocked) return true
if (name in sellable) return false   // 在售且没买 → 一律拒绝
```

另外**删掉了批量预下载**：原 `LaunchedEffect(unlockedActions)` 为每个买过的动作下载其所在 pack，
实测 10 个解锁动作触发 85MB（core 43 + small 35 + text 6.6）。现在只在
"当前播放的 act 未就绪"时后台拉单个 act。

---

## 五、显示偏移：改素材是错误方向

鲸鱼娘在投喂页"偏左下"。先尝试**改素材帧**（逐帧按 alpha bbox 重新对齐脚底和水平中心），
跑了 30 分钟重新编码后效果更差：裁边、腾空位移丢失、每帧抖动。

**实测数据**（`stand` 帧在 360x480 画布内的 alpha bbox）：

| 角色 | bbox | 内容占比 | 中心x | 脚底 |
|---|---|---|---|---|
| 鲸鱼娘 | (15, 98, 350, 474) | 93% × 78% | 182.5 | 474 |
| 大肥鱼 | (0, 12, 360, 480) | 100% × 98% | 180.0 | 480 |
| 小河灵 | (102, 15, 267, 469) | 46% × 95% | 184.5 | 469 |

鲸鱼娘素材本身其实是正的（中心只偏 +2.5px），"偏"更多来自**视觉重心**
（裙摆左铺、尾巴右甩）+ 舞台留白。

**已采用的方案**：manifest 每角色下发 `display={offsetX, offsetY, scale}`（offset 为画布宽高百分比），
`PetAvatar` 绘制时应用。改服务端文件即生效，不用发版、不动素材。

两个必须注意的点：
- **只给投喂页大角色开 `applyDisplay=true`**。缩略图（商店/图鉴）和聊天页小宠物保持原比例，
  否则套用 0.5 会变得极小。
- scale 不能"统一给同一个数"。大肥鱼原始内容已占 98% 高度，鲸鱼娘只占 78%，
  同样 scale 观感差一截。要按内容占比折算：
  `dsh_scale = (whale_content_h * whale_scale) / dsh_content_h ≈ 0.402`（鲸鱼娘用 0.5）。

---

## 六、PyPI 相关的小坑（本机环境）

- 服务端 `.venv` 里没有 pip，装包要用 `uv pip install --python .venv/Scripts/python.exe <pkg>`
- 配置目录不是项目内 `config/`，而是 platformdirs 的
  `C:\Users\<user>\AppData\Local\musiic-cli\music\`（`pet_content/`、`pets.json` 都在这里）
- Git Bash 的 `/tmp` 和 Windows Python 看到的路径不是同一个，临时文件统一用 `%LOCALAPPDATA%\Temp`

---

## 七、改数据前务必留备份

批量改素材/配置前先 `cp -r` 或重命名成 `.bak`。本轮改素材帧时中途判断失误，
靠 `.zip.bak` 才恢复回来；改 `pets.json`（发音符、调等级）同理，先停服务再改，
避免和运行中的服务写冲突。
