/**
 * 复制到播放列表、下载进度弹窗
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast } from '../utils.js';
import { icon } from '../icons.js';
import { cancelDownload, downloadTrackRequest, fetchDownloadProgress } from '../api.js';
import { addTrackToPlaylist } from '../playlistOps.js';
import { getSelectedTracks } from '../selectionState.js';

// ===================== 复制到播放列表 =====================

export function openCopyModal() {
    const tracks = getSelectedTracks();
    if (tracks.length === 0) return;

    const list = els.copyModalList;
    list.innerHTML = '';
    state.playlists.filter(p => !p.is_system).forEach(p => {
        const btn = document.createElement('button');
        btn.className = 'btn btn-ghost justify-start';
        btn.innerHTML = `${icon(p.is_default ? 'heart' : 'playlist', { filled: p.is_default })} ${p.name}`;
        btn.addEventListener('click', () => copySelectedToPlaylist(p.id));
        list.appendChild(btn);
    });

    els.copyModal.classList.add('modal-open');
    state.copyModalOpen = true;
}

export function closeCopyModal() {
    els.copyModal.classList.remove('modal-open');
    state.copyModalOpen = false;
}

async function copySelectedToPlaylist(playlistId) {
    const tracks = getSelectedTracks();
    closeCopyModal();
    showToast(`正在复制 ${tracks.length} 首到目标列表...`);
    for (const track of tracks) {
        await addTrackToPlaylist(playlistId, track);
    }
    showToast('复制完成', 'success');
    state.selectedIds.clear();
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}

// ===================== 下载进度 =====================

export function openDownloadModal(track) {
    els.downloadModalTitle.textContent = `${track.artist} - ${track.title}`;
    els.downloadModalStatus.textContent = '准备下载...';
    els.downloadModalProgress.style.width = '0%';
    els.downloadModal.classList.add('modal-open');
}

export function closeDownloadModal() {
    els.downloadModal.classList.remove('modal-open');
}

function updateDownloadModal(status, progress) {
    const statusMap = {
        pending: '等待中...',
        running: '下载中...',
        completed: '下载完成',
        failed: '下载失败',
        cancelled: '已取消'
    };
    els.downloadModalStatus.textContent = statusMap[status] || status;
    els.downloadModalProgress.style.width = `${progress}%`;
}

export async function cancelActiveDownload() {
    const task = state.activeDownload;
    if (!task) { closeDownloadModal(); return; }
    try {
        await cancelDownload(task.task_id);
    } catch (err) {
        console.error('取消下载失败:', err);
    }
    task.cancelled = true;
    closeDownloadModal();
    state.activeDownload = null;
    showToast('已取消下载', 'info');
}

async function pollDownloadProgress(taskId) {
    return new Promise((resolve, reject) => {
        const task = state.activeDownload;
        const checkCancelled = () => task && task.cancelled;
        const interval = setInterval(async () => {
            if (checkCancelled()) {
                clearInterval(interval);
                resolve('cancelled');
                return;
            }
            try {
                const data = await fetchDownloadProgress(taskId);
                if (task) updateDownloadModal(data.status, data.progress || 0);
                if (data.status === 'completed') {
                    clearInterval(interval);
                    resolve('completed');
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    reject(new Error(data.error || '下载失败'));
                } else if (data.status === 'cancelled') {
                    clearInterval(interval);
                    resolve('cancelled');
                }
            } catch (err) {
                clearInterval(interval);
                reject(err);
            }
        }, 500);
    });
}

export async function downloadTrack(track, { silent = false, wait = false } = {}) {
    if (!silent) showToast('开始下载...');
    try {
        const data = await downloadTrackRequest(track, 'audio');

        if (data.from_cache) {
            if (!silent) showToast('下载完成（来自缓存）', 'success');
            return;
        }

        if (!data.task_id) {
            if (!silent) showToast('下载失败', 'error');
            return;
        }

        if (!silent || wait) {
            if (!silent) {
                state.activeDownload = { task_id: data.task_id, cancelled: false };
                openDownloadModal(track);
            }
            try {
                const result = await pollDownloadProgress(data.task_id);
                if (!silent) {
                    state.activeDownload = null;
                    if (result === 'completed') {
                        updateDownloadModal('completed', 100);
                        setTimeout(closeDownloadModal, 800);
                        showToast('下载完成', 'success');
                    } else if (result === 'cancelled') {
                        showToast('已取消下载', 'info');
                    }
                }
            } catch (err) {
                if (!silent) {
                    state.activeDownload = null;
                    closeDownloadModal();
                    showToast(err.message || '下载失败', 'error');
                }
                throw err;
            }
        }
    } catch (err) {
        if (!silent) showToast('下载失败', 'error');
    }
}
