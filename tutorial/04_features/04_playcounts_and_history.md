# 04-04 播放统计与收听频率

Musiic 会记录每首歌被播放的次数，并在搜索页、播放列表页显示一个小耳机徽章。这一篇讲统计逻辑和存储方式。

## 什么时候记一次播放

前端 `player.js` 在播放进度达到 **80%** 时触发：

```js
export function updateProgress() {
    ...
    if (state.currentTrack && audio.currentTime / audio.duration >= 0.8) {
        recordPlayProgress(state.currentTrack, audio.currentTime / audio.duration);
    }
    ...
}

function recordPlayProgress(track, progress) {
    if (state.playRecordedForTrackId === track.id) return;
    state.playRecordedForTrackId = track.id;
    recordPlay(track, progress)
        .then(() => refreshPlayCounts())
        .catch(err => console.error('记录播放失败:', err));
}
```

- 80% 是为了避免随便点开一下就统计。
- 一首歌在一次播放过程中只记录一次（`playRecordedForTrackId`）。

## 后端记录接口

```python
@app.post("/api/plays")
def api_record_play(req: PlayRecordRequest):
    try:
        _library.record_play(req.track_id)
    except KeyError:
        # 如果库里没有这首歌，但前端提供了完整 track，先创建 Song
        if req.track is not None:
            song = _track_to_song(req.track)
            _library.add_song(song)
            _library.record_play(req.track_id)
        else:
            raise HTTPException(status_code=404, detail="曲目不存在")

    song = _library.get_song(req.track_id)
    return {"track_id": req.track_id, "count": song.play_count if song else 0}
```

`/api/preview` 也会在成功播放时自动 `record_play`：

```python
_library.record_play(song.id)
```

## Library 里的 play_count

`Song` 模型里有一个字段 `play_count`。`record_play` 的实现通常是在 `library.py` 里：

```python
def record_play(self, song_id: str) -> None:
    song = self.get_song(song_id)
    if song is None:
        raise KeyError(song_id)
    song.play_count += 1
    self.add_song(song)  # 触发持久化
```

每次 `add_song` 都会把 library 写回 `library/library.json`，所以播放次数会永久保存。

## 前端显示收听次数

```js
export function getPlayCountBadge(trackId) {
    const count = state.playCounts[trackId] || 0;
    if (count <= 0) return '';
    return `<span class="badge ..." title="已收听 ${count} 次">${icon('headphones')} ${count}</span>`;
}
```

`trackCard.js` 在渲染每首歌时会调用它，把徽章放在歌曲信息行里。

## 刷新收听频率

页面初始化时：

```js
refreshPlayCounts();
```

`refreshPlayCounts` 调用 `/api/plays` 拿到全部次数，更新 `state.playCounts`，然后触发 `musiic:playcounts-updated` 事件，搜索页和播放列表页自动重绘。

## 为什么播放统计要放在后端

- `localStorage` 只能存本设备的数据，换手机就丢了。
- 后端统一计数，收藏列表里也能看到次数。
- 以后想做「最常播放」歌单也更容易。

## 小结

- 播放达到 80% 才统计，一首歌一次播放只记一次。
- 后端 `Song.play_count` 持久化到 `library.json`。
- 前端通过 `/api/plays` 批量获取，显示耳机徽章。

下一篇讲部署架构。
