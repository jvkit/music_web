/**
 * Musiic H5 入口
 */

import { cacheElements, els } from './dom.js';
import { state } from './state.js';
import { loadSettings, showToast } from './utils.js';
import { fetchWebSources } from './api.js';
import { refreshPlayCounts, restorePlaybackState, savePlaybackState } from './player.js';
import { toggleFavorite } from './playlistOps.js';
import { loadPlaylists, renderPlaylists, handleCreatePlaylist, handleDeletePlaylist } from './views/playlists.js';
import { refreshLibrary } from './playlistOps.js';
import { loadLocal } from './views/local.js';
import { handleSearch } from './views/search.js';
import { saveSettingsFromUI, renderSettings } from './views/settings.js';
import { openCopyModal, closeCopyModal, cancelActiveDownload } from './views/modals.js';
import { handleSelectAll } from './selection.js';
import { initPasswordGate, initAdminPasswordModal } from './passwordGate.js';
import {
    togglePlayPause,
    playPrev,
    playNext,
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
    renderSourceChips();
    await restorePlaybackState();
});

function bindEvents() {
    els.searchBtn.addEventListener('click', handleSearch);
    els.searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') handleSearch(); });

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    document.querySelectorAll('.source-chip').forEach(chip => {
        chip.addEventListener('click', () => setSearchSource(chip.dataset.value));
    });

    if (els.webSourceDropdownBtn) {
        els.webSourceDropdownBtn.addEventListener('click', e => {
            e.stopPropagation();
            const dropdown = els.webSourceDropdownBtn.closest('.dropdown');
            if (dropdown) dropdown.classList.toggle('dropdown-open');
        });
        document.addEventListener('click', e => {
            const dropdown = els.webSourceDropdownBtn.closest('.dropdown');
            if (dropdown && !dropdown.contains(e.target)) {
                dropdown.classList.remove('dropdown-open');
            }
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
        toggleFavorite(state.currentTrack);
    });
    els.lyricsRemoveBtn.addEventListener('click', removeCurrentLocalTrack);

    els.settingsSaveBtn.addEventListener('click', saveSettingsFromUI);

    els.playPauseBtn.addEventListener('click', togglePlayPause);
    els.prevBtn.addEventListener('click', playPrev);
    els.nextBtn.addEventListener('click', playNext);
    els.modeBtn.addEventListener('click', togglePlaybackMode);
    els.playerFavoriteBtn.addEventListener('click', () => {
        if (!state.currentTrack) { showToast('请先选择一首歌曲'); return; }
        toggleFavorite(state.currentTrack);
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
}

function renderTabs() {
    switchTab(state.currentTab);
}

function setSearchSource(source) {
    state.searchSource = source;
    renderSourceChips();
}

async function loadWebSources() {
    try {
        const data = await fetchWebSources();
        state.webSources = data.items || [];
        renderWebSourceMenu();
        renderSourceChips();
        // 音源分类播放列表依赖 webSources 元数据，加载后重新构建
        await refreshLibrary();
    } catch (err) {
        console.error('加载网页音源失败:', err);
    }
}

function renderWebSourceMenu() {
    if (!els.webSourceMenu) return;
    if (state.webSources.length === 0) {
        els.webSourceMenu.innerHTML = '<li class="disabled"><a>暂无网页音源</a></li>';
        return;
    }
    els.webSourceMenu.innerHTML = state.webSources.map(s => `
        <li>
            <a class="web-source-item" data-value="${s.id}" data-name="${s.display_name}">
                <span class="flex-1">${s.display_name}</span>
                ${s.status === 'unstable' ? '<span class="text-orange-500 text-xs">（不稳定）</span>' : ''}
                ${s.direct_stream ? '<span class="text-yellow-500">⭐</span>' : ''}
            </a>
        </li>
    `).join('');

    els.webSourceMenu.querySelectorAll('.web-source-item').forEach(item => {
        item.addEventListener('click', () => {
            setSearchSource(item.dataset.value);
            showToast(`已切换到 ${item.dataset.name}`);
        });
    });
}

function renderSourceChips() {
    document.querySelectorAll('.source-chip').forEach(chip => {
        const active = chip.dataset.value === state.searchSource;
        chip.classList.toggle('btn-primary', active);
        chip.classList.toggle('btn-ghost', !active);
    });

    if (els.webSourceDropdownBtn) {
        const isWeb = state.searchSource.startsWith('web_');
        els.webSourceDropdownBtn.classList.toggle('btn-primary', isWeb);
        els.webSourceDropdownBtn.classList.toggle('btn-ghost', !isWeb);
        const selected = state.webSources.find(s => s.id === state.searchSource);
        const label = els.webSourceDropdownBtn.querySelector('span');
        if (label) {
            label.textContent = selected ? `网页：${selected.display_name}${selected.status === 'unstable' ? '（不稳定）' : ''}${selected.direct_stream ? '⭐' : ''}` : '网页音源';
        }
    }
}

export { switchTab, renderTabs, setSearchSource };
