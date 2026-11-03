/**
 * 播放器核心：音频/视频播放、队列、播放模式、歌词同步
 *
 * audio 元素由 store 持有（非响应式），播放状态全部响应式化供组件绑定。
 */

import { defineStore } from 'pinia';
import {
    API_BASE,
    DEFAULT_THUMBNAIL,
    LS_PLAYBACK_STATE_KEY,
    MODE_LABELS,
    PLAYBACK_MODES,
    getThumbnailUrl,
} from '../lib/config.js';
import {
    formatTime,
    loadFromStorage,
    saveToStorage,
} from '../lib/utils.js';
import { showToast } from '../lib/notify.js';
import {
    fetchPlayCounts,
    previewTrack,
    recordPlay,
    fetchLyrics,
    searchTracks,
} from '../lib/api.js';
import { useLibraryStore } from './library.js';
import { useSearchStore } from './search.js';
import { useServerLibraryStore } from './serverLibrary.js';
import { useLocalStore } from './local.js';
import { useRoomStore } from './room.js';
import { useDiscoverStore } from './discover.js';
import { useRecognizeStore } from './recognize.js';
import { requireAdminPassword } from './ui.js';

let audio = null;
let lastPlaybackSaveTime = 0;

// 歌词本地缓存：有歌词 7 天，无歌词 6 小时（避免每次打开歌词页都重复请求/闪中间态）
const LYRICS_CACHE_PREFIX = 'yinhe_lyrics_';
const LYRICS_TTL = 7 * 24 * 3600 * 1000;
const LYRICS_EMPTY_TTL = 6 * 3600 * 1000;

function readLyricsCache(trackId) {
    try {
        const raw = localStorage.getItem(LYRICS_CACHE_PREFIX + trackId);
        if (!raw) return null;
        const data = JSON.parse(raw);
        const lines = Array.isArray(data.lines) ? data.lines : [];
        const ttl = lines.length ? LYRICS_TTL : LYRICS_EMPTY_TTL;
        if (Date.now() - (data.ts || 0) > ttl) {
            localStorage.removeItem(LYRICS_CACHE_PREFIX + trackId);
            return null;
        }
        return { lines, source: data.source || null };
    } catch {
        return null;
    }
}

function writeLyricsCache(trackId, lines, source) {
    try {
        localStorage.setItem(
            LYRICS_CACHE_PREFIX + trackId,
            JSON.stringify({ lines: lines || [], source: source || null, ts: Date.now() }),
        );
    } catch {
        // 存储满/隐私模式：缓存失败不影响主流程
    }
}

function getAudio() {
    if (!audio) {
        audio = new Audio();
        audio.preload = 'none';
    }
    return audio;
}

async function setShareUrl(track) {
    try {
        const resp = await fetch(`${API_BASE}/share`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(track),
        });
        if (!resp.ok) throw new Error('创建分享码失败');
        const { code } = await resp.json();
        const url = new URL(window.location.href);
        url.searchParams.set('c', code);
        url.searchParams.delete('share');
        url.searchParams.delete('song');
        history.replaceState(null, '', url.toString());
    } catch (err) {
        console.error('setShareUrl 失败:', err);
    }
}

function clearShareUrl() {
    try {
        const url = new URL(window.location.href);
        url.searchParams.delete('share');
        url.searchParams.delete('song');
        url.searchParams.delete('c');
        history.replaceState(null, '', url.toString());
    } catch {
        // ignore
    }
}

// 换源兜底：原音源取流失败时，按歌名在稳定源重新搜索（元数据歌常见场景）
const FALLBACK_SOURCES = ['netease', 'web_liumingye'];

export const usePlayerStore = defineStore('player', {
    state: () => ({
        currentTrack: null,
        isPlaying: false,
        queue: [],
        queueIndex: -1,
        playbackMode: 'list-loop',
        randomHistory: [],
        loadingTrackId: null,
        playRecordedForTrackId: null,
        playCounts: {},
        currentTime: 0,
        duration: 0,
        lyrics: [],
        lyricsSource: null,
        lyricsOpen: false,
        streamFallback: null,
        video: { open: false, title: '', url: '' },
    }),

    getters: {
        modeCfg: (s) => MODE_LABELS[s.playbackMode] || MODE_LABELS['list-loop'],
        playCountOf: (s) => (trackId) => s.playCounts[trackId] || 0,
        currentLocalItem() {
            if (!this.currentTrack) return null;
            return useLocalStore().findLocalItem(this.currentTrack.id);
        },
    },

    actions: {
        // ===================== 初始化：绑定 audio 事件 =====================

        init() {
            const el = getAudio();
            el.addEventListener('timeupdate', () => this.onTimeUpdate());
            el.addEventListener('loadedmetadata', () => { this.duration = el.duration || 0; });
            el.addEventListener('ended', () => this.handleTrackEnded());
            el.addEventListener('error', () => this.handleAudioError());
            el.addEventListener('play', () => { this.isPlaying = true; this.updateMediaSession(); });
            el.addEventListener('pause', () => { this.savePlaybackState(); });
            window.addEventListener('beforeunload', () => this.savePlaybackState());
        },

        onTimeUpdate() {
            const el = getAudio();
            this.currentTime = el.currentTime || 0;
            if (!el.duration) return;
            if (this.currentTrack && el.currentTime / el.duration >= 0.8) {
                this.recordPlayProgress(this.currentTrack, el.currentTime / el.duration);
            }
            const now = Date.now();
            if (now - lastPlaybackSaveTime > 5000) {
                this.savePlaybackState();
                lastPlaybackSaveTime = now;
            }
        },

        // ===================== 播放控制 =====================

        togglePlayPause() {
            const room = useRoomStore();
            if (!this.currentTrack) { showToast('请先选择一首歌曲'); return; }
            const el = getAudio();
            if (this.isPlaying) {
                el.pause();
                this.isPlaying = false;
                if (room.isInRoom && !room.applyingRemote) room.sendPause(el.currentTime || 0);
            } else {
                el.play().catch(() => showToast('播放失败', 'error'));
                this.isPlaying = true;
                if (room.isInRoom && !room.applyingRemote) room.sendPlay(el.currentTime || 0);
            }
            this.updateMediaSession();
            this.savePlaybackState();
        },

        updateMediaSession() {
            if (!('mediaSession' in navigator)) return;

            if (this.currentTrack) {
                const t = this.currentTrack;
                const artwork = t.thumbnail
                    ? [{ src: getThumbnailUrl(t.thumbnail), sizes: '512x512', type: 'image/jpeg' }]
                    : [];
                navigator.mediaSession.metadata = new MediaMetadata({
                    title: t.title,
                    artist: t.artist,
                    album: t.album || '',
                    artwork,
                });
            } else {
                navigator.mediaSession.metadata = null;
            }

            navigator.mediaSession.playbackState = this.isPlaying ? 'playing' : 'paused';

            try {
                navigator.mediaSession.setActionHandler('play', () => this.togglePlayPause());
                navigator.mediaSession.setActionHandler('pause', () => this.togglePlayPause());
                navigator.mediaSession.setActionHandler('previoustrack', () => this.playPrev());
                navigator.mediaSession.setActionHandler('nexttrack', () => this.playNext());
            } catch (e) {
                // 部分浏览器不支持某些 action，忽略
            }
        },

        stopPlayback() {
            const el = getAudio();
            el.pause();
            el.src = '';
            el.currentTime = 0;
            this.currentTime = 0;
            this.duration = 0;
            this.currentTrack = null;
            this.isPlaying = false;
            this.queueIndex = -1;
            this.streamFallback = null;
            this.updateMediaSession();
            this.savePlaybackState();
        },

        async removeCurrentLocalTrack() {
            if (!this.currentTrack) return;
            const local = useLocalStore();
            const localItem = local.findLocalItem(this.currentTrack.id);
            if (!localItem) return;
            const ok = await requireAdminPassword('删除本地文件');
            if (!ok) return;
            if (!confirm('确定删除该本地文件吗？')) return;

            if (this.currentTrack.id === localItem.id || this.currentTrack.id === localItem.track?.id) {
                if (this.queue.length > 1) this.playNext();
                else this.stopPlayback();
            }

            try {
                const { deleteLocalItem } = await import('../lib/api.js');
                await deleteLocalItem(localItem.id);
                showToast('已删除', 'success');
                await local.load();
            } catch (err) {
                showToast('删除失败', 'error');
            }
        },

        async tryPlayLocal(track, context = 'search') {
            const local = useLocalStore();
            await local.load();
            const localItem = local.findLocalItem(track.id);
            if (!localItem) return false;

            if (localItem.media_type === 'video') {
                this.playLocalItem(localItem);
                return true;
            }

            const el = getAudio();
            this.currentTrack = track;
            this.isPlaying = true;
            this.playRecordedForTrackId = null;
            this.streamFallback = null;
            el.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
            el.play().catch(err => {
                console.error('本地播放失败:', err);
                showToast('本地播放失败', 'error');
                this.isPlaying = false;
            });
            this.updateMediaSession();
            this.savePlaybackState();
            return true;
        },

        queueForContext(context, track) {
            if (context === 'search') return [...useSearchStore().results];
            if (context === 'playlist') return [...useLibraryStore().getCurrentPlaylistTracks()];
            if (context === 'server') return [...useServerLibraryStore().items];
            if (context === 'discover') return [...useDiscoverStore().queueTracks];
            if (context === 'recognize') return [...useRecognizeStore().results];
            return [track];
        },

        async playTrack(track, context = 'search', preferStream = null, { allowFallback = true } = {}) {
            const room = useRoomStore();
            if (this.loadingTrackId === track.id) return;
            this.loadingTrackId = track.id;

            this.queue = this.queueForContext(context, track) || [track];
            this.queueIndex = this.queue.findIndex(t => t.id === track.id);
            this.randomHistory = [];

            const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));
            const local = useLocalStore();
            const localItem = local.findLocalItem(track.id);

            const el = getAudio();

            if (localItem) {
                this.loadingTrackId = null;
                this.currentTrack = track;
                this.isPlaying = true;
                this.playRecordedForTrackId = null;
                this.streamFallback = null;
                el.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
                el.play().catch(err => {
                    console.error('播放失败:', err);
                    showToast('播放失败', 'error');
                    this.isPlaying = false;
                });
                this.updateMediaSession();
                this.savePlaybackState();
                if (room.isInRoom && !room.applyingRemote) room.sendChangeTrack(track);
                return;
            }

            showToast('正在加载试听...');
            try {
                const data = await previewTrack(track, 'audio', useStream);
                if (this.loadingTrackId !== track.id) return;
                if (data.fallback && data.track) {
                    track = data.track;
                    showToast(`原音源不可用，已通过 ${data.source} 播放`, 'info');
                }
                this.currentTrack = track;
                this.isPlaying = true;
                this.playRecordedForTrackId = null;
                this.streamFallback = data.streamed ? { track, context, isVideo: false, tried: !useStream } : null;

                el.src = data.stream_url;
                el.play().catch(err => {
                    console.error('播放失败:', err);
                    showToast('播放失败', 'error');
                    this.isPlaying = false;
                });

                this.updateMediaSession();
                this.savePlaybackState();
                if (room.isInRoom && !room.applyingRemote) room.sendChangeTrack(track);
            } catch (err) {
                if (this.loadingTrackId !== track.id) return;
                console.error('网络加载失败，尝试本地文件:', err);
                const played = await this.tryPlayLocal(track, context);
                if (played) {
                    showToast('已切换到本地文件', 'success');
                } else if (allowFallback) {
                    await this.fallbackPlay(track);
                } else {
                    showToast('加载失败，本地无该歌曲', 'error');
                }
            } finally {
                if (this.loadingTrackId === track.id) this.loadingTrackId = null;
            }
        },

        /** 原音源失败后的换源兜底：按歌名在稳定源逐源逐候选重搜并播放 */
        async fallbackPlay(track) {
            showToast('原音源加载失败，正在换源重试…', 'warning');
            const query = `${track.title || ''} ${track.artist || ''}`.trim();
            if (!query) {
                showToast('加载失败：原音源不可用', 'error');
                return false;
            }
            for (const source of FALLBACK_SOURCES) {
                if (source === track.source) continue;
                let candidates = [];
                try {
                    candidates = (await searchTracks(query, source, 5, 0)).tracks || [];
                } catch {
                    continue;
                }
                for (const matched of candidates.filter(t => t.id !== track.id).slice(0, 3)) {
                    const ok = await this.playTrackByQueueTrack(matched, null, { allowFallback: false, quiet: true });
                    if (ok) {
                        showToast(`已通过其他音源播放（${source}）`, 'success');
                        return true;
                    }
                }
            }
            showToast('加载失败：原音源不可用，且未找到可播放的替代', 'error');
            return false;
        },

        async playVideo(track, preferStream = true) {
            const room = useRoomStore();
            if (room.isInRoom) { showToast('房间模式下暂不支持 MV', 'warning'); return; }
            showToast('正在加载 MV...');
            try {
                const data = await previewTrack(track, 'video', preferStream);
                this.video = { open: true, title: `${track.artist} - ${track.title}`, url: data.stream_url };
                this.streamFallback = data.streamed ? { track, context: 'search', isVideo: true, tried: !preferStream } : null;
            } catch (err) {
                // previewTrack 静默失败
            }
        },

        closeVideoModal() {
            this.video = { open: false, title: '', url: '' };
        },

        async playLocalItem(item) {
            if (!item.track) return;
            const room = useRoomStore();
            this.loadingTrackId = null;

            if (item.media_type === 'video') {
                if (room.isInRoom) { showToast('房间模式下暂不支持 MV', 'warning'); return; }
                this.video = {
                    open: true,
                    title: `${item.track.artist} - ${item.track.title}`,
                    url: `${API_BASE}/local/stream/${encodeURIComponent(item.id)}`,
                };
                return;
            }

            const local = useLocalStore();
            const el = getAudio();
            this.currentTrack = item.track;
            this.isPlaying = true;
            this.queue = local.items.filter(i => i.track).map(i => i.track);
            this.queueIndex = this.queue.findIndex(t => t.id === item.track.id);
            this.randomHistory = [];
            this.streamFallback = null;
            this.playRecordedForTrackId = null;

            el.src = `${API_BASE}/local/stream/${encodeURIComponent(item.id)}`;
            el.play().catch(err => {
                console.error('播放失败:', err);
                showToast('播放失败', 'error');
                this.isPlaying = false;
            });

            this.updateMediaSession();
            this.savePlaybackState();
            if (room.isInRoom && !room.applyingRemote) room.sendChangeTrack(item.track);
        },

        setQueue(queue, queueIndex) {
            this.queue = queue;
            this.queueIndex = queueIndex;
        },

        // ===================== 队列与播放模式 =====================

        togglePlaybackMode() {
            const idx = PLAYBACK_MODES.indexOf(this.playbackMode);
            this.playbackMode = PLAYBACK_MODES[(idx + 1) % PLAYBACK_MODES.length];
            this.savePlaybackState();
        },

        playPrev() {
            if (this.queue.length === 0) { showToast('没有上一首'); return; }
            if (this.playbackMode === 'list-random') {
                if (this.randomHistory.length > 1) {
                    this.randomHistory.pop();
                    const prevId = this.randomHistory[this.randomHistory.length - 1];
                    const track = this.queue.find(t => t.id === prevId);
                    if (track) this.playTrackByQueueTrack(track);
                }
                return;
            }
            this.queueIndex = (this.queueIndex - 1 + this.queue.length) % this.queue.length;
            this.playTrackByQueueTrack(this.queue[this.queueIndex]);
            this.savePlaybackState();
        },

        playNext() {
            if (this.queue.length === 0) { showToast('没有下一首'); return; }

            if (this.playbackMode === 'list-random') {
                const remaining = this.queue.filter(t => !this.randomHistory.includes(t.id));
                let nextTrack;
                if (remaining.length === 0) {
                    this.randomHistory = [];
                    nextTrack = this.queue[Math.floor(Math.random() * this.queue.length)];
                } else {
                    nextTrack = remaining[Math.floor(Math.random() * remaining.length)];
                }
                this.randomHistory.push(nextTrack.id);
                this.playTrackByQueueTrack(nextTrack);
                this.savePlaybackState();
                return;
            }

            this.queueIndex = (this.queueIndex + 1) % this.queue.length;
            this.playTrackByQueueTrack(this.queue[this.queueIndex]);
            this.savePlaybackState();
        },

        async playTrackByQueueTrack(track, preferStream = null, { allowFallback = true, quiet = false } = {}) {
            if (!track) return false;
            const room = useRoomStore();
            if (this.loadingTrackId === track.id) return false;
            this.loadingTrackId = track.id;

            // 同步队列索引：从右侧「接下来播放」等处直接点歌时，高亮要跟着走
            const queueIdx = this.queue.findIndex((t) => t.id === track.id);
            if (queueIdx >= 0) this.queueIndex = queueIdx;

            this.currentTrack = track;
            this.isPlaying = true;
            this.playRecordedForTrackId = null;

            const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));
            const el = getAudio();

            const localItem = useLocalStore().findLocalItem(track.id);
            if (localItem) {
                this.loadingTrackId = null;
                el.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
                this.streamFallback = null;
            } else {
                try {
                    const data = await previewTrack(track, 'audio', useStream);
                    if (this.loadingTrackId !== track.id) return false;
                    if (data.fallback && data.track) {
                        track = data.track;
                        this.currentTrack = track;
                        showToast(`原音源不可用，已通过 ${data.source} 播放`, 'info');
                    }
                    el.src = data.stream_url;
                    this.streamFallback = data.streamed ? { track, context: 'queue', isVideo: false, tried: !useStream } : null;
                } catch (err) {
                    if (this.loadingTrackId !== track.id) return false;
                    console.error('队列加载失败，尝试本地文件:', err);
                    const played = await this.tryPlayLocal(track, 'queue');
                    if (played) {
                        showToast('已切换到本地文件', 'success');
                    } else if (allowFallback) {
                        this.loadingTrackId = null;
                        const ok = await this.fallbackPlay(track);
                        if (!ok) {
                            this.isPlaying = false;
                        }
                        return ok;
                    } else {
                        if (!quiet) showToast('加载失败，本地无该歌曲', 'error');
                        this.loadingTrackId = null;
                        this.isPlaying = false;
                        return false;
                    }
                }
            }

            this.loadingTrackId = null;
            el.play().catch(err => {
                console.error('播放失败:', err);
                showToast('播放失败', 'error');
                this.isPlaying = false;
            });

            this.updateMediaSession();
            this.savePlaybackState();
            if (room.isInRoom && !room.applyingRemote) room.sendChangeTrack(track);
            return true;
        },

        handleTrackEnded() {
            if (!this.currentTrack || this.queue.length === 0) return;
            this.recordPlayProgress(this.currentTrack, 1.0);

            if (this.playbackMode === 'single-loop') {
                const el = getAudio();
                el.currentTime = 0;
                el.play().catch(() => showToast('播放失败', 'error'));
                return;
            }
            this.playNext();
        },

        // ===================== 进度与歌词 =====================

        seekTo(position) {
            const el = getAudio();
            if (!el.duration) return;
            el.currentTime = position;
            this.currentTime = position;
            const room = useRoomStore();
            if (room.isInRoom && !room.applyingRemote) room.sendSeek(el.currentTime);
            this.savePlaybackState();
        },

        seekRatio(ratio) {
            const el = getAudio();
            if (!el.duration) return;
            this.seekTo(Math.max(0, Math.min(1, ratio)) * el.duration);
        },

        async loadLyricsFor(track) {
            if (!track) return;
            const cached = readLyricsCache(track.id);
            if (cached) {
                this.lyrics = cached.lines;
                this.lyricsSource = cached.source;
                return;
            }
            this.lyrics = [];
            this.lyricsSource = null;
            try {
                const data = await fetchLyrics(track);
                // 请求期间可能已切歌：只应用仍是当前曲目的结果
                if (this.currentTrack?.id !== track.id) return;
                const lines = data.has_lyrics ? (data.lines || []) : [];
                const source = data.source || track.source;
                this.lyrics = lines;
                this.lyricsSource = source;
                writeLyricsCache(track.id, lines, source);
            } catch {
                if (this.currentTrack?.id !== track.id) return;
                this.lyrics = [];
                this.lyricsSource = null;
            }
        },

        async openLyricsPage() {
            if (!this.currentTrack) { showToast('请先选择一首歌曲'); return; }
            const track = this.currentTrack;
            this.lyricsOpen = true;
            document.title = `${track.title} - ${track.artist} | 音河`;
            await setShareUrl(track);
            await this.loadLyricsFor(track);
        },

        closeLyricsPage() {
            if (!this.lyricsOpen) return;
            this.lyricsOpen = false;
            clearShareUrl();
            document.title = '音河 · 发现你的下一首歌';
        },

        // ===================== 错误处理 =====================

        async handleAudioError() {
            if (this.currentTrack) {
                const played = await this.tryPlayLocal(this.currentTrack, this.streamFallback?.context || 'search');
                if (played) {
                    showToast('网络流失败，已切换到本地文件', 'success');
                    return;
                }
            }

            if (this.streamFallback && !this.streamFallback.tried) {
                this.streamFallback.tried = true;
                const { track, context, isVideo } = this.streamFallback;
                showToast('边下边播失败，回退到下载后播放...', 'warning');
                if (isVideo) {
                    await this.playVideo(track, false);
                } else {
                    await this.playTrack(track, context, false);
                }
                return;
            }
            console.error('音频播放错误:', getAudio().error);
            showToast('播放失败', 'error');
            this.isPlaying = false;
        },

        async handleVideoError() {
            if (this.streamFallback && this.streamFallback.isVideo && !this.streamFallback.tried) {
                this.streamFallback.tried = true;
                const { track } = this.streamFallback;
                showToast('边下边播失败，回退到下载后播放...', 'warning');
                await this.playVideo(track, false);
                return;
            }
            console.error('视频播放错误');
            showToast('视频播放失败', 'error');
        },

        // ===================== 播放频率统计 =====================

        recordPlayProgress(track, progress) {
            if (!track) return;
            if (this.playRecordedForTrackId === track.id) return;
            this.playRecordedForTrackId = track.id;
            recordPlay(track, progress)
                .then(() => this.refreshPlayCounts())
                .catch(err => console.error('记录播放失败:', err));
        },

        async refreshPlayCounts() {
            try {
                const data = await fetchPlayCounts();
                this.playCounts = data.items || {};
            } catch (err) {
                console.error('加载收听频率失败:', err);
            }
        },

        // ===================== 播放状态持久化 =====================

        savePlaybackState() {
            if (!this.currentTrack) {
                saveToStorage(LS_PLAYBACK_STATE_KEY, null);
                return;
            }
            const el = getAudio();
            const payload = {
                playlistId: useLibraryStore().currentPlaylistId,
                track: this.currentTrack,
                isPlaying: this.isPlaying,
                currentTime: el.currentTime || 0,
                playbackMode: this.playbackMode,
                queueIndex: this.queueIndex,
                timestamp: Date.now(),
            };
            saveToStorage(LS_PLAYBACK_STATE_KEY, payload);
        },

        async restorePlaybackState() {
            const saved = loadFromStorage(LS_PLAYBACK_STATE_KEY, null);
            if (!saved) return;

            if (saved.playbackMode && PLAYBACK_MODES.includes(saved.playbackMode)) {
                this.playbackMode = saved.playbackMode;
            }

            const library = useLibraryStore();
            library.currentPlaylistId = saved.playlistId || 'default';

            if (saved.track) {
                const playlist = library.playlists.find(p => p.id === library.currentPlaylistId);
                if (playlist && playlist.tracks.length > 0) {
                    this.queue = [...playlist.tracks];
                } else {
                    this.queue = [saved.track];
                }
                this.queueIndex = Math.max(0, this.queue.findIndex(t => t.id === saved.track.id));

                this.currentTrack = saved.track;

                const el = getAudio();
                try {
                    const localItem = useLocalStore().findLocalItem(saved.track.id);
                    if (localItem) {
                        el.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
                    } else {
                        const data = await previewTrack(saved.track, 'audio', true);
                        el.src = data.stream_url;
                    }

                    const resume = () => {
                        if (saved.currentTime) {
                            try { el.currentTime = saved.currentTime; } catch (e) {}
                        }
                        if (saved.isPlaying) {
                            this.isPlaying = true;
                            el.play().catch(() => {
                                this.isPlaying = false;
                            });
                        } else {
                            this.isPlaying = false;
                        }
                    };

                    if (el.readyState >= 1) {
                        resume();
                    } else {
                        const onLoaded = () => {
                            el.removeEventListener('loadedmetadata', onLoaded);
                            resume();
                        };
                        el.addEventListener('loadedmetadata', onLoaded);
                    }
                } catch (err) {
                    console.error('恢复播放状态失败:', err);
                    this.isPlaying = false;
                }
            }
        },

        // ===================== 一起听：远程状态应用 =====================

        async applyRoomState(changes) {
            const room = useRoomStore();
            if (changes.trackChanged) {
                const track = room.currentTrack;
                if (!track || !track.id) return;
                if (this.currentTrack && this.currentTrack.id === track.id) return;
                room.applyingRemote = true;
                try {
                    await this.playTrack(track, 'room');
                } catch (err) {
                    console.error('同步房间曲目失败:', err);
                    showToast('房间同步失败', 'error');
                } finally {
                    room.applyingRemote = false;
                }
            } else if (changes.playStateChanged || changes.seekChanged) {
                if (!this.currentTrack) return;
                room.applyingRemote = true;
                try {
                    const el = getAudio();
                    let targetPosition = room.position || 0;
                    if (room.isPlaying && room.updatedAt) {
                        targetPosition += Math.max(0, Date.now() / 1000 - room.updatedAt);
                    }
                    if (el.duration && targetPosition > el.duration) {
                        targetPosition = el.duration;
                    }
                    if (el.currentTime != null && Math.abs(el.currentTime - targetPosition) > 1.5) {
                        el.currentTime = targetPosition;
                    }
                    if (room.isPlaying) {
                        el.play().catch(() => {
                            // 移动端自动播放被拦截时保持暂停，用户可手动点播放
                        });
                        this.isPlaying = true;
                    } else {
                        el.pause();
                        this.isPlaying = false;
                    }
                    this.savePlaybackState();
                } finally {
                    room.applyingRemote = false;
                }
            }
        },
    },
});

export { getAudio, formatTime, DEFAULT_THUMBNAIL };
