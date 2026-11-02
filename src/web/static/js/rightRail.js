/**
 * 右侧栏：Now Playing、播放队列、音源标签
 */

import { state } from './state.js';
import { formatTime, getThumbnailUrl, showToast } from './utils.js';
import { icon } from './icons.js';
import { togglePlayPause, playNext, playTrackByQueueTrack } from './player.js';
import { toggleFavorite, isTrackInPlaylist, getFavoriteTargetId } from './playlistOps.js';

let els = {};

export function initRightRail() {
    els = {
        title: document.getElementById('nowTitle'),
        artist: document.getElementById('nowArtist'),
        cover: document.getElementById('nowCover'),
        sidePlay: document.getElementById('sidePlay'),
        nowNext: document.getElementById('nowNextBtn'),
        nowFav: document.getElementById('nowFavoriteBtn'),
        nowTime: document.getElementById('nowTime'),
        nowProgress: document.getElementById('nowProgress'),
        queueList: document.getElementById('queueList'),
        queueClear: document.getElementById('queueClear'),
        tags: document.getElementById('discoverTags'),
        sourceCount: document.getElementById('sourceCount'),
    };

    if (els.sidePlay) els.sidePlay.addEventListener('click', togglePlayPause);
    if (els.nowNext) els.nowNext.addEventListener('click', playNext);
    if (els.queueClear) {
        els.queueClear.addEventListener('click', () => {
            state.queue = [];
            state.queueIndex = -1;
            renderQueue();
            showToast('已清空播放队列');
        });
    }
    if (els.nowFav) {
        els.nowFav.addEventListener('click', async () => {
            if (!state.currentTrack) { showToast('请先选择一首歌曲', 'warning'); return; }
            await toggleFavorite(state.currentTrack);
            renderNowPlaying();
        });
    }

    const audio = document.getElementById('audioPlayer');
    if (audio) {
        audio.addEventListener('timeupdate', updateTime);
        audio.addEventListener('loadedmetadata', updateTime);
        audio.addEventListener('play', updatePlayIcon);
        audio.addEventListener('pause', updatePlayIcon);
    }

    document.addEventListener('musiic:player-info', renderNowPlaying);
    document.addEventListener('musiic:queue-updated', renderQueue);
    document.addEventListener('musiic:playlists-updated', renderNowPlaying);

    renderNowPlaying();
    renderQueue();
}

export function renderNowPlaying() {
    if (!els.title) return;
    const track = state.currentTrack;
    if (!track) {
        els.title.textContent = '未在播放';
        els.artist.textContent = '选一首歌开始';
        els.cover.style.backgroundImage = '';
        els.cover.innerHTML = icon('music');
        els.cover.classList.remove('playing');
        if (els.sidePlay) els.sidePlay.innerHTML = icon('play');
        if (els.nowFav) els.nowFav.className = 'ctrl';
        renderTime(0, 0);
        return;
    }

    els.title.textContent = track.title || '未知歌曲';
    els.artist.textContent = track.artist || '-';
    const cover = getThumbnailUrl(track.thumbnail);
    els.cover.innerHTML = '';
    els.cover.style.backgroundImage = `url("${cover}")`;
    els.cover.classList.toggle('playing', state.isPlaying);

    if (els.sidePlay) els.sidePlay.innerHTML = icon(state.isPlaying ? 'pause' : 'play');
    if (els.nowFav) {
        const fav = isTrackInPlaylist(track.id, getFavoriteTargetId(track));
        els.nowFav.className = fav ? 'ctrl liked' : 'ctrl';
        els.nowFav.innerHTML = icon('heart', { filled: fav });
    }
    const audio = document.getElementById('audioPlayer');
    renderTime(audio ? audio.currentTime : 0, audio ? audio.duration : 0);
}

function updatePlayIcon() {
    if (!els.sidePlay) return;
    els.sidePlay.innerHTML = icon(state.isPlaying ? 'pause' : 'play');
    if (els.cover) els.cover.classList.toggle('playing', state.isPlaying);
}

function updateTime() {
    const audio = document.getElementById('audioPlayer');
    if (!audio) return;
    renderTime(audio.currentTime || 0, audio.duration || 0);
}

function renderTime(current, duration) {
    if (els.nowProgress) {
        const pct = duration ? (current / duration) * 100 : 0;
        els.nowProgress.style.width = `${Math.min(100, pct)}%`;
    }
    if (els.nowTime) {
        els.nowTime.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
    }
}

export function renderQueue() {
    if (!els.queueList) return;
    els.queueList.innerHTML = '';
    const queue = state.queue || [];
    if (queue.length === 0) {
        els.queueList.innerHTML = '<div class="queue-empty">队列是空的</div>';
        return;
    }
    queue.slice(0, 40).forEach((track, index) => {
        const item = document.createElement('button');
        item.className = `queue-item${index === state.queueIndex ? ' current' : ''}`;
        item.innerHTML = `
            <span class="queue-cover">${track.thumbnail ? `<img src="${getThumbnailUrl(track.thumbnail)}" alt="">` : icon('music')}</span>
            <span class="queue-copy"><strong>${escapeText(track.title || '未知歌曲')}</strong><span>${escapeText(track.artist || '-')}</span></span>
            <span class="queue-number">${String(index + 1).padStart(2, '0')}</span>
        `;
        item.addEventListener('click', () => playTrackByQueueTrack(track));
        els.queueList.appendChild(item);
    });
}

export function renderSourceTags() {
    if (!els.tags) return;
    const sources = state.webSources || [];
    els.tags.innerHTML = '';
    if (els.sourceCount) els.sourceCount.textContent = `${sources.length} 个网页源`;
    sources.slice(0, 12).forEach(src => {
        const tag = document.createElement('button');
        tag.className = 'tag';
        tag.textContent = src.display_name || src.id;
        tag.addEventListener('click', () => {
            state.searchSource = src.id;
            document.dispatchEvent(new CustomEvent('musiic:source-selected', { detail: src.id }));
        });
        els.tags.appendChild(tag);
    });
}

function escapeText(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}
