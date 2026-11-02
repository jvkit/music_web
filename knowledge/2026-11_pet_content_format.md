# 宠物素材热更新格式（manifest v3，2026-11）

目标：**上新角色 / 新动作 / 调价格 / 调随机货架都不需要客户端发版**，只改服务器
`config/pet_content/`。客户端兑换动作后按 `pack` 下载对应 zip。

## 目录结构

```
config/pet_content/
├── manifest.json
├── whale_girl/act1.zip
└── dsh_pet/
    ├── act1.zip   # core
    ├── act2.zip   # small
    ├── act3.zip   # play
    └── ...
```

- 每个 zip 内必须是 `frames/frame_0000.webp`、`frames/frame_0001.webp` …（4 位补零、从 0000 连续）。
- 画布必须 3:4（当前 360×480）；透明 WebP。
- 一个 pack 可以包含多个 act；一个 act 只属于一个 pack。

## manifest.json

```json
{
  "version": 3,
  "shop_rotation_version": 1,
  "characters": {
    "dsh_pet": {
      "name": "大肥鱼",
      "fps": 12,
      "builtin": false,
      "acts": ["act1"],
      "roles": {
        "idle": ["stand"],
        "music": ["music"],
        "click": ["heart"],
        "move": ["螃蟹走路"],
        "turn": ["东张西望"],
        "drag": ["被鼠标拖拽悬空反馈"],
        "sleep_start": ["睡觉-开始"],
        "sleep_loop": ["睡觉-循环"],
        "sleep_end": ["睡觉-起来"],
        "events": {
          "balance": ["余额-钱袋满溢", "..."],
          "whisper": ["碎碎念-擦桌碎碎念", "..."],
          "workStatus": ["工作状态-思考冒泡", "..."]
        }
      },
      "starter": ["stand", "music", "heart", "bounce", "stretch", "睡觉-开始", "睡觉-循环", "睡觉-起来"],
      "behaviors": {
        "weights": { "idle": 10, "turn": 5, "move": 5 },
        "categories": [
          { "id": "小动作", "weight": 20, "actions": ["照镜子", "写代码"] },
          { "id": "玩耍", "weight": 20, "actions": ["玩水枪"] }
        ]
      },
      "clips": {
        "stand": { "act": 1, "start": 0, "end": 119, "fps": 12, "mode": "loop" },
        "照镜子": { "act": 2, "start": 0, "end": 119 }
      },
      "packs": [
        { "id": "core", "name": "核心动作", "acts": ["act1"], "size": 0, "sha256": "", "frames": 1800 },
        { "id": "small", "name": "小动作", "acts": ["act2"], "size": 0, "sha256": "", "frames": 1440 }
      ]
    }
  },
  "actions": [
    {
      "id": "照镜子",
      "character": "dsh_pet",
      "name": "照镜子",
      "category": "小动作",
      "clip": "照镜子",
      "min_level": 1,
      "pack": "small"
    }
  ],
  "shop": [
    { "species": "whale_girl", "name": "鲸鱼娘", "price": 300, "level_required": 5 },
    { "species": "dsh_pet", "name": "大肥鱼", "price": 800, "level_required": 12 }
  ]
}
```

### 关键字段

| 字段 | 说明 |
|---|---|
| `version` | 素材总版本；改任何帧/角色都要 +1，客户端清旧缓存 |
| `shop_rotation_version` | 动作货架轮换版本；+1 会重随机未售货架，已售动作保留 |
| `roles` | 语义角色：引擎只认这些槽位，不再写死 clip 名 |
| `starter` | 兑换角色即赠送的动作（待机、听歌、基础互动、睡觉） |
| `behaviors` | 待机/随机池权重；`categories[].actions` 只放可售卖动作 |
| `clips` | 动作帧区间；`mode` 支持 `loop/once/pingpong/reverse`，`fps` 可单独覆盖 |
| `packs` | 下载分片：客户端按动作所属 pack 懒下载 |
| `actions` | 动作商店目录；`min_level` 控制货架候选，价格由服务端随机 |

## 动作商店随机规则

- 每个宠物对、每个等级一个货架，首次打开时生成并写入 `pets.json`，之后**固定不变**。
- 每层 4~6 个动作，价格从 `{10,20,30,40}` 随机。
- 候选 = 当前角色 `min_level <= 等级`、未拥有、未在其它货架的动作。
- 随机种子 = `pair_key + level + shop_rotation_version`，同一对好友稳定。
- `POST /pet/buy_action` 扣音符、标记 sold、写入 `action_unlocks[species]`。
- 服务器发新内容时改 `shop_rotation_version`：未售货架重随机，已购动作永久保留。

## 新角色 / 新动作流程

1. 帧序列打 zip：`zip -r actN.zip frames/`（`ZIP_STORED` 即可，WebP 已压缩）。
2. 放到 `config/pet_content/<character>/actN.zip`。
3. manifest：
   - 加 `characters.<id>`，补齐 `roles/starter/behaviors/clips/packs`；
   - 新动作加到 `actions`，指定 `pack` 和 `min_level`；
   - 需要售卖角色就加到 `shop`；
   - `version` +1。
4. 不用重启服务、不用发客户端。
5. 验证：
   - `GET /api/pet/content/manifest`
   - `GET /api/pet/content/file/<character>/actN`
   - App 进宠物中心拉清单，兑换后自动下载对应 pack。

## 兼容

- `boy` 可标 `builtin: true`、`acts: []`，客户端直接用 assets 内置素材，不请求 zip。
- 旧版 App 只读 `characters.clips` 和 `acts`，仍可运行；新字段被忽略。
- 已下架角色（miao/wang/tiao）不放进 `shop`；旧数据切到这些 species 时客户端回退 boy。
