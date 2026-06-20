/**
 * Musiic H5 入口
 */

import { cacheElements, els } from './dom.js';
import { state } from './state.js';
import { loadSettings, showToast } from './utils.js';
import { API_BASE } from './config.js';
import { fetchWebSources, searchTracks, fetchLocalItems } from './api.js';

// 音源四大分类
const SOURCE_GROUPS = [
    {
        id: 'recommended',
        name: '强烈推荐',
        sources: ['web_liumingye']
    },
    {
        id: 'stable',
        name: '稳定源',
        sources: ['netease', 'bilibili', 'web_gequbao', 'web_fangpi']
    },
    {
        id: 'direct',
        name: '直连源（可播性一般）',
        sources: ['web_jbsou', 'web_netease_fe_mm']
    },
    {
        id: 'unstable',
        name: '不稳定 / 备选',
        sources: ['web_qqmp3', 'web_musicenc', 'web_tonzhon', 'web_tonzhon_whamon']
    },
    {
        id: 'foreign',
        name: '外网源',
        sources: ['youtube', 'soundcloud']
    }
];

const NATIVE_SOURCE_NAMES = {
    youtube: 'YouTube',
    netease: '网易云',
    bilibili: 'Bilibili',
    soundcloud: 'SoundCloud'
};
import { refreshPlayCounts, restorePlaybackState, savePlaybackState } from './player.js';
import { toggleFavorite, getFavoriteTargetId, isTrackInPlaylist } from './playlistOps.js';
import { icon } from './icons.js';
import { loadPlaylists, renderPlaylists, handleCreatePlaylist, handleDeletePlaylist } from './views/playlists.js';
import { refreshLibrary } from './playlistOps.js';
import { loadLocal } from './views/local.js';
import { handleSearch } from './views/search.js';
import { saveSettingsFromUI, renderSettings } from './views/settings.js';
import { openCopyModal, closeCopyModal, cancelActiveDownload } from './views/modals.js';
import { handleSelectAll } from './selection.js';
import { initPasswordGate, initAdminPasswordModal } from './passwordGate.js';
import { initRoomUI, openRoomModal } from './components/roomPanel.js';
import { connectRoom, checkRoomExists } from './room.js';
import {
    togglePlayPause,
    playPrev,
    playNext,
    playTrack,
    togglePlaybackMode,
    updateProgress,
    updateDuration,
    seekProgress,
    openLyricsPage,
    closeVideoModal,
    closeLyricsPage,
    renderPlaybackMode,
    removeCurrentLocalTrack,
    handleAudioError,
    handleVideoError,
    handleTrackEnded
} from './player.js';

document.addEventListener('DOMContentLoaded', async () => {
    initPasswordGate();
    initAdminPasswordModal();
    cacheElements();
    bindEvents();
    loadSettings();
    await loadWebSources();
    await loadPlaylists();
    refreshPlayCounts();
    await loadLocal();
    renderTabs();
    renderSettings();
    renderPlaybackMode();
    renderSourceSelect();
    await restorePlaybackState();
    await handleShareFromUrl();
    initRoomUI();
    promptJoinFromUrl();
});

async function handleShareFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const shareParam = params.get('share') || params.get('song');
    if (!shareParam) return;

    let track;
    try {
        const base64 = shareParam.replace(/-/g, '+').replace(/_/g, '/');
        const json = decodeURIComponent(escape(atob(base64)));
        const data = JSON.parse(json);
        track = {
            id: data.i || data.id,
            title: data.t || data.title,
            artist: data.a || data.artist,
            source: data.s || data.source,
            source_url: data.u || data.source_url,
            thumbnail: data.p || data.thumbnail,
            cover_url: data.c || data.cover_url,
            duration: data.d || data.duration,
            extra: data.extra || {},
            lyrics: null,
            media_type: 'audio',
        };
        if (!track.id || !track.title) return;
    } catch (err) {
        console.error('分享链接解析失败:', err);
        return;
    }

    // 立即显示启动屏，挡住搜索首页，避免先闪现再跳转
    if (els.shareSplash) els.shareSplash.classList.remove('hidden');

    const hideSplash = () => {
        if (els.shareSplash) els.shareSplash.classList.add('hidden');
    };

    // 1) 优先按 id 从本地库找
    try {
        const localData = await fetchLocalItems();
        const locals = localData.items || [];
        const localItem = locals.find(i => i.track && i.track.id === track.id);
        if (localItem && localItem.track) {
            await playTrack(localItem.track, 'local', null);
            openLyricsPage();
            hideSplash();
            return;
        }
    } catch {
        // ignore
    }

    // 2) 尝试通过 source+id 解析完整 track
    try {
        const resp = await fetch(`${API_BASE}/track_resolve?source=${encodeURIComponent(track.source)}&track_id=${encodeURIComponent(track.id)}`);
        if (resp.ok) {
            const resolved = await resp.json();
            if (resolved && resolved.title && resolved.title !== resolved.id) {
                await playTrack(resolved, 'search', null);
                openLyricsPage();
                hideSplash();
                return;
            }
        }
    } catch (err) {
        console.error('分享 track 解析失败:', err);
    }

    // 3) 按歌名+歌手搜索兜底
    try {
        const data = await searchTracks(`${track.title} ${track.artist || ''}`.trim(), track.source, 5, 0);
        const results = data.tracks || [];
        const matched = results.find(t => t.id === track.id) || results[0];
        if (matched) {
            await playTrack(matched, 'search', null);
            openLyricsPage();
            hideSplash();
            return;
        }
    } catch (err) {
        console.error('分享歌曲搜索兜底失败:', err);
    }

    hideSplash();
    showToast('分享歌曲无法播放，请手动搜索', 'error');
}

async function promptJoinFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const roomId = params.get('room');
    if (!roomId) return;
    // 清理 URL，避免刷新重复提示
    const url = new URL(window.location.href);
    url.searchParams.delete('room');
    window.history.replaceState({}, '', url);

    const exists = await checkRoomExists(roomId);
    if (!exists) {
        showToast('邀请链接中的房间不存在', 'error');
        return;
    }
    openRoomModal(roomId);
    showToast(`邀请你加入房间 ${roomId}`, 'success');
}

function bindEvents() {
    els.searchBtn.addEventListener('click', () => { switchTab('search'); handleSearch(); });
    els.searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') { switchTab('search'); handleSearch(); } });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    // 兜底：用事件委托处理 Tab 切换，防止某些移动端点击图标不触发
    if (els.tabNav) {
        els.tabNav.addEventListener('click', e => {
            const btn = e.target.closest('.tab-btn');
            if (btn && btn.dataset.tab) switchTab(btn.dataset.tab);
        });
    }

    if (els.sourceSelect) {
        els.sourceSelect.addEventListener('change', () => {
            const value = els.sourceSelect.value;
            if (value) setSearchSource(value);
        });
    }

    els.selectAll.addEventListener('change', handleSelectAll);
    els.copyToPlaylistBtn.addEventListener('click', openCopyModal);

    els.createPlaylistBtn.addEventListener('click', handleCreatePlaylist);
    els.deletePlaylistBtn.addEventListener('click', handleDeletePlaylist);

    els.copyModalCancel.addEventListener('click', closeCopyModal);
    els.copyModal.addEventListener('click', e => { if (e.target === els.copyModal) closeCopyModal(); });

    els.downloadModalCancel.addEventListener('click', cancelActiveDownload);
    els.downloadModal.addEventListener('click', e => { if (e.target === els.downloadModal) cancelActiveDownload(); });

    els.videoModalClose.addEventListener('click', closeVideoModal);
    els.videoModal.addEventListener('click', e => { if (e.target === els.videoModal) closeVideoModal(); });
    els.videoPlayer.addEventListener('error', handleVideoError);

    els.playerLyricsBtn.addEventListener('click', openLyricsPage);
    els.playerRemoveBtn.addEventListener('click', removeCurrentLocalTrack);
    els.lyricsModalClose.addEventListener('click', closeLyricsPage);
    els.lyricsPrevBtn.addEventListener('click', playPrev);
    els.lyricsNextBtn.addEventListener('click', playNext);
    els.lyricsPlayPauseBtn.addEventListener('click', togglePlayPause);
    els.lyricsModeBtn.addEventListener('click', togglePlaybackMode);
    els.lyricsFavoriteBtn.addEventListener('click', () => {
        if (!state.currentTrack) { showToast('请先选择一首歌曲'); return; }
        const t = state.currentTrack;
        const targetId = getFavoriteTargetId(t);
        const next = !isTrackInPlaylist(t.id, targetId);
        els.lyricsFavoriteBtn.innerHTML = icon('heart', { filled: next });
        els.lyricsFavoriteBtn.className = next
            ? 'btn btn-circle btn-ghost text-error'
            : 'btn btn-circle btn-ghost text-white';
        toggleFavorite(t).catch(() => {});
    });
    els.lyricsRemoveBtn.addEventListener('click', removeCurrentLocalTrack);

    els.settingsSaveBtn.addEventListener('click', saveSettingsFromUI);

    els.playPauseBtn.addEventListener('click', togglePlayPause);
    els.prevBtn.addEventListener('click', playPrev);
    els.nextBtn.addEventListener('click', playNext);
    els.modeBtn.addEventListener('click', togglePlaybackMode);
    els.playerFavoriteBtn.addEventListener('click', () => {
        if (!state.currentTrack) { showToast('请先选择一首歌曲'); return; }
        const t = state.currentTrack;
        const targetId = getFavoriteTargetId(t);
        const next = !isTrackInPlaylist(t.id, targetId);
        els.playerFavoriteBtn.innerHTML = icon('heart', { filled: next });
        els.playerFavoriteBtn.className = next
            ? 'btn btn-circle btn-ghost btn-sm text-error'
            : 'btn btn-circle btn-ghost btn-sm text-base-content/40';
        if (els.lyricsFavoriteBtn) {
            els.lyricsFavoriteBtn.innerHTML = icon('heart', { filled: next });
            els.lyricsFavoriteBtn.className = next
                ? 'btn btn-circle btn-ghost text-error'
                : 'btn btn-circle btn-ghost text-white';
        }
        toggleFavorite(t).catch(() => {});
    });

    els.audioPlayer.addEventListener('timeupdate', updateProgress);
    els.audioPlayer.addEventListener('loadedmetadata', updateDuration);
    els.audioPlayer.addEventListener('ended', handleTrackEnded);
    els.audioPlayer.addEventListener('error', handleAudioError);
    els.audioPlayer.addEventListener('pause', () => {
        savePlaybackState();
    });
    els.progressContainer.addEventListener('click', seekProgress);

    window.addEventListener('beforeunload', () => {
        savePlaybackState();
    });
}

// ===================== Tab 切换 =====================

function switchTab(tab) {
    state.currentTab = tab;

    document.querySelectorAll('.tab-btn').forEach(btn => {
        const active = btn.dataset.tab === tab;
        btn.classList.toggle('tab-active', active);
    });

    ['search', 'playlists', 'local', 'settings'].forEach(name => {
        els[`${name}View`].classList.toggle('hidden', name !== tab);
    });

    if (tab === 'playlists') renderPlaylists();
    if (tab === 'local') loadLocal();
    if (tab === 'settings') renderSettings();

    if (tab === 'search' || tab === 'playlists') {
        els.batchBar.classList.remove('hidden');
        document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
    } else {
        els.batchBar.classList.add('hidden');
    }

    if (tab === 'search') {
        requestAnimationFrame(() => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
            if (els.searchInput) els.searchInput.focus({ preventScroll: true });
        });
    }
}

function renderTabs() {
    switchTab(state.currentTab);
}

function setSearchSource(source) {
    state.searchSource = source;
    renderSourceSelect();
}

function getSourceName(sourceId) {
    if (NATIVE_SOURCE_NAMES[sourceId]) return NATIVE_SOURCE_NAMES[sourceId];
    const ws = state.webSources.find(s => s.id === sourceId);
    if (!ws) return sourceId;
    let name = ws.display_name;
    if (ws.direct_stream) name += ' ⭐';
    if (ws.status === 'unstable') name += '（不稳定）';
    return name;
}

async function loadWebSources() {
    try {
        const data = await fetchWebSources();
        state.webSources = data.items || [];
        state.hiddenSources = data.hidden_sources || [];
        renderSourceSelect();
        // 音源分类播放列表依赖 webSources 元数据，加载后重新构建
        await refreshLibrary();
    } catch (err) {
        console.error('加载网页音源失败:', err);
    }
}

function renderSourceSelect() {
    if (!els.sourceSelect) return;

    const hidden = new Set(state.hiddenSources || []);

    const options = SOURCE_GROUPS.map(group => {
        const opts = group.sources
            .filter(id => !hidden.has(id))
            .filter(id => state.webSources.length === 0 || id.startsWith('web_') ? state.webSources.some(s => s.id === id) : true)
            .map(id => {
                const selected = state.searchSource === id ? 'selected' : '';
                return `<option value="${id}" ${selected}>${getSourceName(id)}</option>`;
            })
            .join('');
        return opts ? `<optgroup label="${group.name}">${opts}</optgroup>` : '';
    }).join('');

    els.sourceSelect.innerHTML = options || '<option value="">无可用音源</option>';
    if (state.searchSource && !hidden.has(state.searchSource)) {
        els.sourceSelect.value = state.searchSource;
    }
}

export { switchTab, renderTabs, setSearchSource };
