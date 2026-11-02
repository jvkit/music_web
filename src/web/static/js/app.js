/**
 * 音河 H5 入口
 */

import { cacheElements, els } from './dom.js';
import { state } from './state.js';
import { loadSettings, showToast } from './utils.js';
import { API_BASE } from './config.js';
import { fetchWebSources, searchTracks, fetchLocalItems } from './api.js';
import { shareTrack } from './qqShare.js';

// 音源四大分类
const SOURCE_GROUPS = [
    { id: 'recommended', name: '强烈推荐', sources: ['web_liumingye'] },
    { id: 'stable', name: '稳定源', sources: ['netease', 'bilibili', 'web_gequbao', 'web_fangpi'] },
    { id: 'direct', name: '直连源（可播性一般）', sources: ['web_jbsou', 'web_netease_fe_mm'] },
    { id: 'unstable', name: '不稳定 / 备选', sources: ['web_qqmp3', 'web_musicenc', 'web_tonzhon', 'web_tonzhon_whamon'] },
    { id: 'foreign', name: '外网源', sources: ['youtube', 'soundcloud'] }
];

const NATIVE_SOURCE_NAMES = {
    youtube: 'YouTube',
    netease: '网易云',
    bilibili: 'Bilibili',
    soundcloud: 'SoundCloud'
};

import { refreshPlayCounts, restorePlaybackState, savePlaybackState } from './player.js';
import { toggleFavorite, getFavoriteTargetId, isTrackInPlaylist, refreshLibrary } from './playlistOps.js';
import { icon } from './icons.js';
import { loadPlaylists, renderPlaylists, handleCreatePlaylist, handleDeletePlaylist, renderSettingsTargetPlaylist } from './views/playlists.js';
import { loadLocal } from './views/local.js';
import { handleSearch, renderSearchResults } from './views/search.js';
import { saveSettingsFromUI, renderSettings } from './views/settings.js';
import { openCopyModal, closeCopyModal, cancelActiveDownload } from './views/modals.js';
import { handleSelectAll } from './selection.js';
import { initPasswordGate, initAdminPasswordModal } from './passwordGate.js';
import { initRoomUI, openRoomModal } from './components/roomPanel.js';
import { checkRoomExists } from './room.js';
import { initAuthUI, renderAuthUser, openAuthModal } from './authUI.js';
import { initRightRail, renderSourceTags } from './rightRail.js';
import { loadServerLibrary, showServerLibrary, showSearchResultsPanel } from './views/serverLibrary.js';
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
    updatePlayerInfo,
    closeVideoModal,
    closeLyricsPage,
    renderPlaybackMode,
    removeCurrentLocalTrack,
    handleAudioError,
    handleVideoError,
    handleTrackEnded
} from './player.js';

const PAGE_META = {
    search: ['发现你的下一首歌', '从熟悉的旋律出发，也多走一点陌生的路。'],
    playlists: ['我的列表', '收藏、歌单与网页收藏都在这里。'],
    local: ['本地音乐', '已经下载到服务器的歌曲。'],
    settings: ['设置', '搜索数量、收藏目标与网页音源。'],
};

document.addEventListener('DOMContentLoaded', async () => {
    initPasswordGate();
    initAdminPasswordModal();
    cacheElements();
    bindEvents();
    loadSettings();
    initAuthUI();
    initRightRail();
    await loadWebSources();
    await loadPlaylists();
    refreshPlayCounts();
    await loadLocal();
    await loadServerLibrary();
    renderTabs();
    renderSettings();
    renderPlaybackMode();
    renderSourceSelect();
    await restorePlaybackState();
    await handleShareFromUrl();
    initRoomUI();
    promptJoinFromUrl();
});

// ===================== 登录态切换：重载数据 =====================
document.addEventListener('yinhe:auth-changed', async e => {
    const loggedIn = !!(e.detail && e.detail.loggedIn);
    state.currentPlaylistId = 'default';
    if (loggedIn) {
        state.selectedIds.clear();
        await loadPlaylists();
        renderSettings();
        renderAuthUser();
    } else {
        await loadPlaylists();
        renderSettings();
        renderAuthUser();
    }
});

// ===================== Tab 切换 =====================

document.addEventListener('musiic:switch-tab', e => {
    if (e.detail) switchTab(e.detail);
});

document.addEventListener('musiic:source-selected', e => {
    setSearchSource(e.detail);
    switchTab('search');
});

function switchTab(tab) {
    closeLyricsPage();

    state.currentTab = tab;

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('tab-active', btn.dataset.tab === tab);
    });

    ['search', 'playlists', 'local', 'settings'].forEach(name => {
        const view = els[`${name}View`];
        if (view) view.classList.toggle('hidden', name !== tab);
    });

    const meta = PAGE_META[tab];
    if (meta && els.pageTitle) {
        els.pageTitle.textContent = meta[0];
        els.pageSub.textContent = meta[1];
    }

    if (tab === 'playlists') renderPlaylists();
    if (tab === 'local') loadLocal();
    if (tab === 'settings') renderSettings();

    if (tab === 'search') {
        if (state.searchQuery) showSearchResultsPanel();
        else showServerLibrary();
        els.batchBar.classList.toggle('hidden', !state.searchQuery);
        if (state.searchQuery) document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
    } else if (tab === 'playlists') {
        els.batchBar.classList.remove('hidden');
        document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
    } else {
        els.batchBar.classList.add('hidden');
    }

    if (tab === 'search') {
        requestAnimationFrame(() => {
            if (els.mainScroll) els.mainScroll.scrollTo({ top: 0, behavior: 'smooth' });
            if (els.searchInput) els.searchInput.focus({ preventScroll: true });
        });
    } else if (els.mainScroll) {
        els.mainScroll.scrollTo({ top: 0 });
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
        renderSourceTags();
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

// ===================== 事件绑定 =====================

function bindEvents() {
    els.searchBtn.addEventListener('click', () => { switchTab('search'); handleSearch(); });
    els.searchInput.addEventListener('keydown', e => {
        if (e.key === 'Enter') { switchTab('search'); handleSearch(); }
    });
    els.searchInput.addEventListener('input', () => {
        if (!els.searchInput.value.trim() && state.searchQuery) {
            state.searchQuery = '';
            state.searchResults = [];
            state.searchHasMore = false;
            if (els.searchResults) els.searchResults.innerHTML = '';
            if (els.batchBar) els.batchBar.classList.add('hidden');
            showServerLibrary();
        }
    });
    document.addEventListener('keydown', e => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            els.searchInput.focus();
            els.searchInput.select();
        }
    });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    if (els.mobileNav) {
        els.mobileNav.addEventListener('click', e => {
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
    if (els.lyricsShareBtn) {
        els.lyricsShareBtn.addEventListener('click', () => {
            shareTrack(state.currentTrack, 0);
        });
    }
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
        updateFavoriteButton(els.playerFavoriteBtn, next);
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
    els.audioPlayer.addEventListener('pause', () => { savePlaybackState(); });
    els.progressContainer.addEventListener('click', seekProgress);

    window.addEventListener('beforeunload', () => { savePlaybackState(); });
}

function updateFavoriteButton(btn, filled) {
    btn.innerHTML = icon('heart', { filled });
    btn.className = filled ? 'heart-btn liked' : 'heart-btn';
}

// ===================== 分享 / 房间链接 =====================

function exitShareEntry() {
    document.documentElement.classList.remove('share-entry');
}

async function handleShareFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const shareParam = params.get('share') || params.get('song');
    const code = params.get('c');

    let track;
    if (code) {
        try {
            const resp = await fetch(`${API_BASE}/share?code=${encodeURIComponent(code)}`);
            if (!resp.ok) throw new Error('分享码失效');
            const data = await resp.json();
            track = { ...data.track, lyrics: null, media_type: 'audio' };
        } catch (err) {
            console.error('分享码解析失败:', err);
            exitShareEntry();
            return;
        }
    } else if (shareParam) {
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
        } catch (err) {
            console.error('分享链接解析失败:', err);
            exitShareEntry();
            return;
        }
    } else {
        exitShareEntry();
        return;
    }

    if (!track || !track.id || !track.title) {
        exitShareEntry();
        return;
    }

    state.currentTrack = track;
    updatePlayerInfo();
    openLyricsPage();
    exitShareEntry();

    const tryPlay = async (candidate) => {
        state.currentTrack = candidate;
        updatePlayerInfo();
        await playTrack(candidate, 'search', null);
        openLyricsPage();
    };

    try {
        const localData = await fetchLocalItems();
        const locals = localData.items || [];
        const localItem = locals.find(i => i.track && i.track.id === track.id);
        if (localItem && localItem.track) {
            await tryPlay(localItem.track);
            return;
        }
    } catch {
        // ignore
    }

    try {
        const resp = await fetch(`${API_BASE}/track_resolve?source=${encodeURIComponent(track.source)}&track_id=${encodeURIComponent(track.id)}`);
        if (resp.ok) {
            const resolved = await resp.json();
            if (resolved && resolved.title && resolved.title !== resolved.id) {
                await tryPlay(resolved);
                return;
            }
        }
    } catch (err) {
        console.error('分享 track 解析失败:', err);
    }

    try {
        const data = await searchTracks(`${track.title} ${track.artist || ''}`.trim(), track.source, 5, 0);
        const results = data.tracks || [];
        const matched = results.find(t => t.id === track.id) || results[0];
        if (matched) {
            await tryPlay(matched);
            return;
        }
    } catch (err) {
        console.error('分享歌曲搜索兜底失败:', err);
    }

    exitShareEntry();
    showToast('分享歌曲无法播放，请手动搜索', 'error');
}

async function promptJoinFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const roomId = params.get('room');
    if (!roomId) return;
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

export { switchTab, renderTabs, setSearchSource };
