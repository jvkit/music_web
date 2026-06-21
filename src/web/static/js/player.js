/**
 * 播放器核心：音频/视频播放、队列、播放模式、歌词同步
 */

import { API_BASE, DEFAULT_THUMBNAIL, LS_PLAYBACK_STATE_KEY, MODE_LABELS, PLAYBACK_MODES } from './config.js';
import { els } from './dom.js';
import { state } from './state.js';
import {
    formatTime,
    getThumbnailUrl,
    loadFromStorage,
    saveToStorage,
    showToast
} from './utils.js';
import { icon } from './icons.js';
import {
    fetchPlayCounts,
    previewTrack,
    recordPlay,
    fetchLyrics
} from './api.js';
import { isTrackInPlaylist, getCurrentPlaylistTracks } from './playlistOps.js';
import { loadLocal } from './views/local.js';
import { isInRoom, sendChangeTrack, sendPlay, sendPause, sendSeek } from './room.js';

let lastPlaybackSaveTime = 0;

function setShareUrl(track) {
    try {
        // 只传必要字段，尽量缩短 URL，避免微信爬虫截断/丢参
        const payload = {
            s: track.source,
            i: track.id,
            t: track.title,
            a: track.artist,
        };
        if (track.source_url) payload.u = track.source_url;
        if (track.thumbnail) payload.p = track.thumbnail;
        if (track.cover_url) payload.c = track.cover_url;
        if (track.duration) payload.d = track.duration;
        const json = JSON.stringify(payload);
        const base64 = btoa(unescape(encodeURIComponent(json)))
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=+$/, '');
        const url = new URL(window.location.href);
        url.searchParams.set('share', base64);
        url.searchParams.delete('song');
        history.replaceState(null, '', url.toString());
    } catch {
        // 分享 URL 不是关键路径，失败静默
    }
}

function clearShareUrl() {
    try {
        const url = new URL(window.location.href);
        url.searchParams.delete('share');
        url.searchParams.delete('song');
        history.replaceState(null, '', url.toString());
    } catch {
        // ignore
    }
}

// ===================== 加载状态（防重复点击） =====================

export function setTrackLoading(trackId) {
    state.loadingTrackId = trackId;
    updateLoadingButtons();
}

export function finishTrackLoading() {
    state.loadingTrackId = null;
    updateLoadingButtons();
}

export function updateLoadingButtons() {
    document.querySelectorAll('.btn-play[data-id]').forEach(btn => {
        const loading = state.loadingTrackId === btn.dataset.id;
        btn.disabled = loading;
        btn.innerHTML = icon(loading ? 'spinner' : 'play', loading ? { className: 'animate-spin' } : {});
    });
}

// ===================== 播放控制 =====================

export function togglePlayPause() {
    if (!state.currentTrack) { showToast('请先选择一首歌曲'); return; }
    if (state.isPlaying) {
        els.audioPlayer.pause();
        state.isPlaying = false;
        if (isInRoom() && !state.room.applyingRemote) sendPause(els.audioPlayer.currentTime || 0);
    } else {
        els.audioPlayer.play().catch(() => showToast('播放失败', 'error'));
        state.isPlaying = true;
        if (isInRoom() && !state.room.applyingRemote) sendPlay(els.audioPlayer.currentTime || 0);
    }
    updatePlayButton();
    savePlaybackState();
}

export function updatePlayButton() {
    els.playPauseBtn.innerHTML = icon(state.isPlaying ? 'pause' : 'play');
    els.lyricsPlayPauseBtn.innerHTML = icon(state.isPlaying ? 'pause' : 'play');
    if (els.lyricsCover) {
        els.lyricsCover.classList.toggle('lyrics-cover-paused', !state.isPlaying);
    }
    updateMediaSession();
}

function updateMediaSession() {
    if (!('mediaSession' in navigator)) return;

    if (state.currentTrack) {
        const t = state.currentTrack;
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

    navigator.mediaSession.playbackState = state.isPlaying ? 'playing' : 'paused';

    try {
        navigator.mediaSession.setActionHandler('play', () => togglePlayPause());
        navigator.mediaSession.setActionHandler('pause', () => togglePlayPause());
        navigator.mediaSession.setActionHandler('previoustrack', () => playPrev());
        navigator.mediaSession.setActionHandler('nexttrack', () => playNext());
    } catch (e) {
        // 部分浏览器不支持某些 action，忽略
    }
}

export function updatePlayerInfo() {
    if (!state.currentTrack) return;
    const t = state.currentTrack;
    els.playerTitle.textContent = t.title;
    els.playerArtist.textContent = t.artist;
    els.playerThumbnail.src = getThumbnailUrl(t.thumbnail);
    updatePlayerFavorite();
    updatePlayerRemoveButton();

    // 歌词页打开时同步更新其 UI
    if (!els.lyricsModal.classList.contains('hidden')) {
        els.lyricsTitle.textContent = t.title;
        els.lyricsArtist.textContent = t.artist;
        els.lyricsBackground.style.backgroundImage = `url(${getThumbnailUrl(t.thumbnail)})`;
        if (els.lyricsCover) {
            els.lyricsCover.src = getThumbnailUrl(t.thumbnail);
        }
    }
}

function getFavoriteTargetId(track) {
    if (track && track.source && track.source.startsWith('web_')) {
        return state.settings.webFavoritePlaylistId || 'web_favorites';
    }
    return state.settings.targetPlaylistId || 'default';
}

export function updatePlayerFavorite() {
    if (!state.currentTrack) {
        els.playerFavoriteBtn.innerHTML = icon('heart');
        els.playerFavoriteBtn.className = 'btn btn-circle btn-ghost btn-sm text-base-content/40';
        if (els.lyricsFavoriteBtn) {
            els.lyricsFavoriteBtn.innerHTML = icon('heart');
            els.lyricsFavoriteBtn.className = 'btn btn-circle btn-ghost text-white';
        }
        return;
    }
    const targetId = getFavoriteTargetId(state.currentTrack);
    const isFavorite = isTrackInPlaylist(state.currentTrack.id, targetId);
    els.playerFavoriteBtn.innerHTML = icon('heart', { filled: isFavorite });
    els.playerFavoriteBtn.className = isFavorite
        ? 'btn btn-circle btn-ghost btn-sm text-error'
        : 'btn btn-circle btn-ghost btn-sm text-base-content/40';
    if (els.lyricsFavoriteBtn) {
        els.lyricsFavoriteBtn.innerHTML = icon('heart', { filled: isFavorite });
        els.lyricsFavoriteBtn.className = isFavorite
            ? 'btn btn-circle btn-ghost text-error'
            : 'btn btn-circle btn-ghost text-white';
    }
}

export function updatePlayerRemoveButton() {
    if (!state.currentTrack) {
        els.playerRemoveBtn.classList.add('hidden');
        if (els.lyricsRemoveBtn) els.lyricsRemoveBtn.classList.add('hidden');
        return;
    }
    const localItem = state.localItems.find(i => i.track && i.track.id === state.currentTrack.id);
    els.playerRemoveBtn.classList.toggle('hidden', !localItem);
    if (els.lyricsRemoveBtn) els.lyricsRemoveBtn.classList.toggle('hidden', !localItem);
}

export function stopPlayback() {
    els.audioPlayer.pause();
    els.audioPlayer.src = '';
    els.audioPlayer.currentTime = 0;
    state.currentTrack = null;
    state.isPlaying = false;
    state.queueIndex = -1;
    state.streamFallback = null;
    updatePlayButton();
    els.playerTitle.textContent = '未在播放';
    els.playerArtist.textContent = '-';
    els.playerThumbnail.src = DEFAULT_THUMBNAIL;
    updatePlayerRemoveButton();
    savePlaybackState();
}

export async function removeCurrentLocalTrack() {
    if (!state.currentTrack) return;
    const localItem = state.localItems.find(i => i.track && i.track.id === state.currentTrack.id);
    if (!localItem) return;
    const { requireAdminPassword } = await import('./passwordGate.js');
    const ok = await requireAdminPassword('删除本地文件');
    if (!ok) return;
    if (!confirm('确定删除该本地文件吗？')) return;

    const deletingId = localItem.id;

    // 删除当前播放歌曲时先切歌或停止
    if (state.currentTrack.id === deletingId) {
        if (state.queue.length > 1) playNext();
        else stopPlayback();
    }

    try {
        const { deleteLocalItem } = await import('./api.js');
        await deleteLocalItem(deletingId);
        showToast('已删除', 'success');
        const { loadLocal } = await import('./views/local.js');
        await loadLocal();
        updatePlayerRemoveButton();
    } catch (err) {
        showToast('删除失败', 'error');
    }
}

async function tryPlayLocal(track, context = 'search') {
    await loadLocal();
    const localItem = state.localItems.find(i => i.track && i.track.id === track.id);
    if (!localItem) return false;

    if (localItem.media_type === 'video') {
        playLocalItem(localItem);
        return true;
    }

    state.currentTrack = track;
    state.isPlaying = true;
    state.playRecordedForTrackId = null;
    state.streamFallback = null;
    els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
    els.audioPlayer.play().catch(err => {
        console.error('本地播放失败:', err);
        showToast('本地播放失败', 'error');
        state.isPlaying = false;
        updatePlayButton();
    });
    updatePlayerInfo();
    updatePlayButton();
    updatePlayerRemoveButton();
    savePlaybackState();
    return true;
}

export async function playTrack(track, context = 'search', preferStream = null) {
    // 防重入：同一曲目正在加载则忽略，切歌时覆盖旧加载
    if (state.loadingTrackId === track.id) return;
    setTrackLoading(track.id);

    if (context === 'search') state.queue = [...state.searchResults];
    else if (context === 'playlist') state.queue = [...getCurrentPlaylistTracks()];
    else if (context === 'local') state.queue = [track];
    else if (context === 'room') state.queue = [track];

    state.queueIndex = state.queue.findIndex(t => t.id === track.id);
    state.randomHistory = [];

    // Bilibili/YouTube/网页音源 默认优先走流（代理或直接 MP3），减少首次播放等待时间；显式传 false 时才强制下载
    const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));

    // 本地已有该歌曲，优先播放本地文件
    const localItem = state.localItems.find(i => i.track && i.track.id === track.id);
    if (localItem) {
        finishTrackLoading();
        state.currentTrack = track;
        state.isPlaying = true;
        state.playRecordedForTrackId = null;
        state.streamFallback = null;
        els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
        els.audioPlayer.play().catch(err => {
            console.error('播放失败:', err);
            showToast('播放失败', 'error');
            state.isPlaying = false;
            updatePlayButton();
        });
        updatePlayerInfo();
        updatePlayButton();
        savePlaybackState();
        if (isInRoom() && !state.room.applyingRemote) sendChangeTrack(track);
        return;
    }

    showToast('正在加载试听...');
    try {
        const data = await previewTrack(track, 'audio', useStream);
        if (state.loadingTrackId !== track.id) return; // 已切歌，丢弃旧结果
        state.currentTrack = track;
        state.isPlaying = true;
        state.playRecordedForTrackId = null;
        state.streamFallback = data.streamed ? { track, context, isVideo: false, tried: !useStream } : null;

        els.audioPlayer.src = data.stream_url;
        els.audioPlayer.play().catch(err => {
            console.error('播放失败:', err);
            showToast('播放失败', 'error');
            state.isPlaying = false;
            updatePlayButton();
        });

        updatePlayerInfo();
        updatePlayButton();
        savePlaybackState();
        if (isInRoom() && !state.room.applyingRemote) sendChangeTrack(track);
    } catch (err) {
        if (state.loadingTrackId !== track.id) return;
        console.error('网络加载失败，尝试本地文件:', err);
        const played = await tryPlayLocal(track, context);
        if (played) {
            showToast('已切换到本地文件', 'success');
        } else {
            showToast('加载失败，本地无该歌曲', 'error');
        }
    } finally {
        if (state.loadingTrackId === track.id) finishTrackLoading();
    }
}

export async function playVideo(track, preferStream = true) {
    if (isInRoom()) { showToast('房间模式下暂不支持 MV', 'warning'); return; }
    showToast('正在加载 MV...');
    try {
        const data = await previewTrack(track, 'video', preferStream);
        els.videoTitle.textContent = `${track.artist} - ${track.title}`;
        els.videoPlayer.src = data.stream_url;
        state.streamFallback = data.streamed ? { track, context: 'search', isVideo: true, tried: !preferStream } : null;
        els.videoModal.classList.remove('hidden');
        els.videoPlayer.play().catch(err => {
            console.error('视频播放失败:', err);
            showToast('视频播放失败', 'error');
        });
    } catch (err) {}
}

export function closeVideoModal() {
    els.videoPlayer.pause();
    els.videoPlayer.src = '';
    els.videoModal.classList.add('hidden');
}

export async function playLocalItem(item) {
    if (!item.track) return;
    finishTrackLoading();

    if (item.media_type === 'video') {
        if (isInRoom()) { showToast('房间模式下暂不支持 MV', 'warning'); return; }
        els.videoTitle.textContent = `${item.track.artist} - ${item.track.title}`;
        els.videoPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(item.id)}`;
        els.videoModal.classList.remove('hidden');
        els.videoPlayer.play().catch(err => {
            console.error('视频播放失败:', err);
            showToast('视频播放失败', 'error');
        });
        return;
    }

    state.currentTrack = item.track;
    state.isPlaying = true;
    state.queue = state.localItems.filter(i => i.track).map(i => i.track);
    state.queueIndex = state.queue.findIndex(t => t.id === item.track.id);
    state.randomHistory = [];
    state.streamFallback = null;
    state.playRecordedForTrackId = null;

    els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(item.id)}`;
    els.audioPlayer.play().catch(err => {
        console.error('播放失败:', err);
        showToast('播放失败', 'error');
        state.isPlaying = false;
        updatePlayButton();
    });

    updatePlayerInfo();
    updatePlayButton();
    savePlaybackState();
    if (isInRoom() && !state.room.applyingRemote) sendChangeTrack(item.track);
}

// ===================== 队列与播放模式 =====================

export function togglePlaybackMode() {
    const idx = PLAYBACK_MODES.indexOf(state.playbackMode);
    state.playbackMode = PLAYBACK_MODES[(idx + 1) % PLAYBACK_MODES.length];
    renderPlaybackMode();
    savePlaybackState();
}

export function renderPlaybackMode() {
    const cfg = MODE_LABELS[state.playbackMode];
    els.modeBtn.innerHTML = `<i class="ph ${cfg.icon}"></i>`;
    els.modeBtn.title = cfg.title;
    if (els.lyricsModeBtn) {
        els.lyricsModeBtn.innerHTML = `<i class="ph ${cfg.icon}"></i>`;
        els.lyricsModeBtn.title = cfg.title;
    }
}

export function playPrev() {
    if (state.queue.length === 0) { showToast('没有上一首'); return; }
    if (state.playbackMode === 'list-random') {
        if (state.randomHistory.length > 1) {
            state.randomHistory.pop();
            const prevId = state.randomHistory[state.randomHistory.length - 1];
            const track = state.queue.find(t => t.id === prevId);
            if (track) playTrackByQueueTrack(track);
        }
        return;
    }
    state.queueIndex = (state.queueIndex - 1 + state.queue.length) % state.queue.length;
    playTrackByQueueTrack(state.queue[state.queueIndex]);
    savePlaybackState();
}

export function playNext() {
    if (state.queue.length === 0) { showToast('没有下一首'); return; }

    if (state.playbackMode === 'list-random') {
        const remaining = state.queue.filter(t => !state.randomHistory.includes(t.id));
        let nextTrack;
        if (remaining.length === 0) {
            state.randomHistory = [];
            nextTrack = state.queue[Math.floor(Math.random() * state.queue.length)];
        } else {
            nextTrack = remaining[Math.floor(Math.random() * remaining.length)];
        }
        state.randomHistory.push(nextTrack.id);
        playTrackByQueueTrack(nextTrack);
        savePlaybackState();
        return;
    }

    state.queueIndex = (state.queueIndex + 1) % state.queue.length;
    playTrackByQueueTrack(state.queue[state.queueIndex]);
    savePlaybackState();
}

export async function playTrackByQueueTrack(track, preferStream = null) {
    if (!track) return;
    if (state.loadingTrackId === track.id) return;
    setTrackLoading(track.id);

    state.currentTrack = track;
    state.isPlaying = true;
    state.playRecordedForTrackId = null;

    const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));

    const localItem = state.localItems.find(i => i.track && i.track.id === track.id);
    if (localItem) {
        finishTrackLoading();
        els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
        state.streamFallback = null;
    } else {
        try {
            const data = await previewTrack(track, 'audio', useStream);
            if (state.loadingTrackId !== track.id) return;
            els.audioPlayer.src = data.stream_url;
            state.streamFallback = data.streamed ? { track, context: 'queue', isVideo: false, tried: !useStream } : null;
        } catch (err) {
            if (state.loadingTrackId !== track.id) return;
            console.error('队列加载失败，尝试本地文件:', err);
            const played = await tryPlayLocal(track, 'queue');
            if (played) {
                showToast('已切换到本地文件', 'success');
            } else {
                showToast('加载失败，本地无该歌曲', 'error');
                finishTrackLoading();
                state.isPlaying = false;
                updatePlayButton();
                return;
            }
        }
    }

    finishTrackLoading();
    els.audioPlayer.play().catch(err => {
        console.error('播放失败:', err);
        showToast('播放失败', 'error');
        state.isPlaying = false;
        updatePlayButton();
    });

    updatePlayerInfo();
    updatePlayButton();
    savePlaybackState();
    if (isInRoom() && !state.room.applyingRemote) sendChangeTrack(track);
}

export function handleTrackEnded() {
    if (!state.currentTrack || state.queue.length === 0) return;
    recordPlayProgress(state.currentTrack, 1.0);

    if (state.playbackMode === 'single-loop') {
        els.audioPlayer.currentTime = 0;
        els.audioPlayer.play().catch(() => showToast('播放失败', 'error'));
        return;
    }
    playNext();
}

// ===================== 进度与歌词 =====================

export function updateProgress() {
    const audio = els.audioPlayer;
    if (!audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    els.progressBar.style.width = `${pct}%`;
    els.currentTime.textContent = formatTime(audio.currentTime);

    if (state.currentTrack && audio.currentTime / audio.duration >= 0.8) {
        recordPlayProgress(state.currentTrack, audio.currentTime / audio.duration);
    }

    syncLyrics(audio.currentTime);

    const now = Date.now();
    if (now - lastPlaybackSaveTime > 5000) {
        savePlaybackState();
        lastPlaybackSaveTime = now;
    }
}

export function updateDuration() {
    els.duration.textContent = formatTime(els.audioPlayer.duration);
}

export function seekProgress(e) {
    const audio = els.audioPlayer;
    if (!audio.duration) return;
    const rect = els.progressContainer.getBoundingClientRect();
    const pct = (e.clientX - rect.left) / rect.width;
    audio.currentTime = pct * audio.duration;
    if (isInRoom() && !state.room.applyingRemote) sendSeek(audio.currentTime);
    savePlaybackState();
}

export async function openLyricsPage() {
    if (!state.currentTrack) { showToast('请先选择一首歌曲'); return; }
    const track = state.currentTrack;
    els.lyricsTitle.textContent = track.title;
    els.lyricsArtist.textContent = track.artist;
    els.lyricsBackground.style.backgroundImage = `url(${getThumbnailUrl(track.thumbnail)})`;
    els.lyricsCover.src = getThumbnailUrl(track.thumbnail);
    els.lyricsCover.classList.toggle('lyrics-cover-paused', !state.isPlaying);
    els.lyricsModal.classList.remove('hidden');
    document.title = `${track.title} - ${track.artist} | 音河`;
    setShareUrl(track);
    updatePlayerFavorite();
    updatePlayerRemoveButton();

    state.lyrics = [];
    state.lyricsSource = null;
    renderLyrics();

    try {
        const data = await fetchLyrics(track);
        state.lyrics = data.has_lyrics ? (data.lines || []) : [];
        state.lyricsSource = data.source || track.source;
        renderLyrics();
    } catch (err) {
        state.lyrics = [];
        state.lyricsSource = null;
        renderLyrics();
    }
}

export function closeLyricsPage() {
    if (els.lyricsModal.classList.contains('hidden')) return;
    els.lyricsModal.classList.add('hidden');
    clearShareUrl();
    document.title = '音河 - 在线音乐';
}

export function renderLyrics() {
    const container = els.lyricsContainer;
    container.innerHTML = '';

    if (!state.lyrics || state.lyrics.length === 0) {
        container.innerHTML = `
            <div class="text-center py-6 text-white/60">
                <p class="text-sm">暂无歌词</p>
                <p class="text-xs text-white/40 mt-1">${state.lyricsSource ? '该音源暂未提供歌词' : '欣赏音乐吧'}</p>
            </div>
        `;
        return;
    }

    state.lyrics.forEach((line, index) => {
        const div = document.createElement('div');
        div.className = 'lyrics-line text-lg text-white/60 transition-all duration-300 cursor-pointer py-1';
        div.dataset.index = index;
        div.dataset.time = line.time;
        div.textContent = line.text || '·';
        if (line.translation) {
            const trans = document.createElement('div');
            trans.className = 'text-sm text-white/40 mt-1';
            trans.textContent = line.translation;
            div.appendChild(trans);
        }
        div.addEventListener('click', () => {
            els.audioPlayer.currentTime = line.time;
        });
        container.appendChild(div);
    });
}

export function syncLyrics(currentTime) {
    if (!state.lyrics || state.lyrics.length === 0) return;
    const lines = els.lyricsContainer.querySelectorAll('.lyrics-line');
    if (!lines.length) return;

    let activeIndex = -1;
    for (let i = 0; i < state.lyrics.length; i++) {
        if (state.lyrics[i].time <= currentTime + 0.2) {
            activeIndex = i;
        } else {
            break;
        }
    }

    lines.forEach((line, index) => {
        if (index === activeIndex) {
            line.className = 'lyrics-line text-xl font-semibold text-white scale-105 transition-all duration-300 cursor-pointer py-2';
            line.scrollIntoView({ behavior: 'smooth', block: 'center' });
        } else {
            line.className = 'lyrics-line text-lg text-white/60 transition-all duration-300 cursor-pointer py-1';
        }
    });
}

// ===================== 错误处理 =====================

export async function handleAudioError() {
    if (state.currentTrack) {
        const played = await tryPlayLocal(state.currentTrack, state.streamFallback?.context || 'search');
        if (played) {
            showToast('网络流失败，已切换到本地文件', 'success');
            return;
        }
    }

    if (state.streamFallback && !state.streamFallback.tried) {
        state.streamFallback.tried = true;
        const { track, context, isVideo } = state.streamFallback;
        showToast('边下边播失败，回退到下载后播放...', 'warning');
        if (isVideo) {
            await playVideo(track, false);
        } else {
            await playTrack(track, context, false);
        }
        return;
    }
    console.error('音频播放错误:', els.audioPlayer.error);
    showToast('播放失败', 'error');
    state.isPlaying = false;
    updatePlayButton();
}

export async function handleVideoError() {
    if (state.streamFallback && state.streamFallback.isVideo && !state.streamFallback.tried) {
        state.streamFallback.tried = true;
        const { track } = state.streamFallback;
        showToast('边下边播失败，回退到下载后播放...', 'warning');
        await playVideo(track, false);
        return;
    }
    console.error('视频播放错误:', els.videoPlayer.error);
    showToast('视频播放失败', 'error');
}

// ===================== 播放频率统计 =====================

function recordPlayProgress(track, progress) {
    if (!track) return;
    if (state.playRecordedForTrackId === track.id) return;
    state.playRecordedForTrackId = track.id;
    recordPlay(track, progress)
        .then(() => refreshPlayCounts())
        .catch(err => console.error('记录播放失败:', err));
}

export async function refreshPlayCounts() {
    try {
        const data = await fetchPlayCounts();
        state.playCounts = data.items || {};
        document.dispatchEvent(new CustomEvent('musiic:playcounts-updated'));
    } catch (err) {
        console.error('加载收听频率失败', err);
    }
}

// ===================== 播放状态持久化 =====================

export function savePlaybackState() {
    if (!state.currentTrack) {
        saveToStorage(LS_PLAYBACK_STATE_KEY, null);
        return;
    }
    const payload = {
        playlistId: state.currentPlaylistId,
        track: state.currentTrack,
        isPlaying: state.isPlaying,
        currentTime: els.audioPlayer.currentTime || 0,
        playbackMode: state.playbackMode,
        queueIndex: state.queueIndex,
        timestamp: Date.now(),
    };
    saveToStorage(LS_PLAYBACK_STATE_KEY, payload);
}

export async function restorePlaybackState() {
    const saved = loadFromStorage(LS_PLAYBACK_STATE_KEY, null);
    if (!saved) {
        state.currentPlaylistId = state.currentPlaylistId || 'default';
        return;
    }

    if (saved.playbackMode && PLAYBACK_MODES.includes(saved.playbackMode)) {
        state.playbackMode = saved.playbackMode;
        renderPlaybackMode();
    }

    state.currentPlaylistId = saved.playlistId || 'default';

    if (saved.track) {
        // 重建队列
        const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
        if (playlist && playlist.tracks.length > 0) {
            state.queue = [...playlist.tracks];
        } else {
            state.queue = [saved.track];
        }
        state.queueIndex = Math.max(0, state.queue.findIndex(t => t.id === saved.track.id));

        state.currentTrack = saved.track;
        updatePlayerInfo();
        updatePlayerFavorite();
        updatePlayerRemoveButton();

        try {
            const localItem = state.localItems.find(i => i.track && i.track.id === saved.track.id);
            if (localItem) {
                els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
            } else {
                const data = await previewTrack(saved.track, 'audio', true);
                els.audioPlayer.src = data.stream_url;
            }

            const resume = () => {
                if (saved.currentTime) {
                    try { els.audioPlayer.currentTime = saved.currentTime; } catch (e) {}
                }
                if (saved.isPlaying) {
                    state.isPlaying = true;
                    els.audioPlayer.play().catch(() => {
                        state.isPlaying = false;
                        updatePlayButton();
                    });
                } else {
                    state.isPlaying = false;
                }
                updatePlayButton();
            };

            if (els.audioPlayer.readyState >= 1) {
                resume();
            } else {
                const onLoaded = () => {
                    els.audioPlayer.removeEventListener('loadedmetadata', onLoaded);
                    resume();
                };
                els.audioPlayer.addEventListener('loadedmetadata', onLoaded);
            }
        } catch (err) {
            console.error('恢复播放状态失败:', err);
            state.isPlaying = false;
            updatePlayButton();
        }
    }

    if (state.currentTab === 'playlists') {
        const { renderPlaylists } = await import('./views/playlists.js');
        renderPlaylists();
    }
}

// ===================== 收藏相关 =====================

document.addEventListener('musiic:playlists-updated', () => {
    updatePlayerFavorite();
});

// ===================== 一起听歌：远程状态应用 =====================

async function applyRemoteTrack(track) {
    if (!track || !track.id) return;
    if (state.currentTrack && state.currentTrack.id === track.id) return;
    state.room.applyingRemote = true;
    try {
        await playTrack(track, 'room');
    } catch (err) {
        console.error('同步房间曲目失败:', err);
        showToast('房间同步失败', 'error');
    } finally {
        state.room.applyingRemote = false;
    }
}

function applyRemotePlayState(isPlaying, position) {
    if (!state.currentTrack) return;
    state.room.applyingRemote = true;
    try {
        const audio = els.audioPlayer;
        let targetPosition = position || 0;
        if (isPlaying && state.room.updatedAt) {
            // 补上从服务端下发到现在经过的时间
            targetPosition += Math.max(0, Date.now() / 1000 - state.room.updatedAt);
        }
        if (audio.duration && targetPosition > audio.duration) {
            targetPosition = audio.duration;
        }
        if (audio.currentTime != null && Math.abs(audio.currentTime - targetPosition) > 1.5) {
            audio.currentTime = targetPosition;
        }
        if (isPlaying) {
            audio.play().catch(() => {
                // 移动端自动播放被拦截时保持暂停，用户可手动点播放
            });
            state.isPlaying = true;
        } else {
            audio.pause();
            state.isPlaying = false;
        }
        updatePlayButton();
        savePlaybackState();
    } finally {
        state.room.applyingRemote = false;
    }
}

document.addEventListener('musiic:room-state', (e) => {
    const { changes } = e.detail;
    if (changes.trackChanged) {
        applyRemoteTrack(state.room.currentTrack);
    } else if (changes.playStateChanged || changes.seekChanged) {
        applyRemotePlayState(state.room.isPlaying, state.room.position);
    }
});
