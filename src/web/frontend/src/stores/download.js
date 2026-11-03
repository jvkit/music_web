/**
 * 下载任务：进度弹窗 + 轮询 + 取消
 */

import { defineStore } from 'pinia';
import { downloadTrackRequest, fetchDownloadProgress, cancelDownload } from '../lib/api.js';
import { showToast } from '../lib/notify.js';

const STATUS_MAP = {
    pending: '等待中...',
    running: '下载中...',
    completed: '下载完成',
    failed: '下载失败',
    cancelled: '已取消'
};

export const useDownloadStore = defineStore('download', {
    state: () => ({
        open: false,
        title: '',
        status: '',
        progress: 0,
        activeTask: null,
    }),
    actions: {
        openModal(track) {
            this.title = `${track.artist} - ${track.title}`;
            this.status = '准备下载...';
            this.progress = 0;
            this.open = true;
        },
        closeModal() {
            this.open = false;
        },
        update(status, progress) {
            this.status = STATUS_MAP[status] || status;
            this.progress = progress;
        },
        async cancel() {
            const task = this.activeTask;
            if (!task) { this.closeModal(); return; }
            try {
                await cancelDownload(task.task_id);
            } catch (err) {
                console.error('取消下载失败:', err);
            }
            task.cancelled = true;
            this.closeModal();
            this.activeTask = null;
            showToast('已取消下载', 'info');
        },

        pollProgress(taskId) {
            return new Promise((resolve, reject) => {
                const task = this.activeTask;
                const interval = setInterval(async () => {
                    if (task && task.cancelled) {
                        clearInterval(interval);
                        resolve('cancelled');
                        return;
                    }
                    try {
                        const data = await fetchDownloadProgress(taskId);
                        this.update(data.status, data.progress || 0);
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
        },

        async downloadTrack(track, { silent = false, wait = false } = {}) {
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
                        this.activeTask = { task_id: data.task_id, cancelled: false };
                        this.openModal(track);
                    }
                    try {
                        const result = await this.pollProgress(data.task_id);
                        if (!silent) {
                            this.activeTask = null;
                            if (result === 'completed') {
                                this.update('completed', 100);
                                setTimeout(() => this.closeModal(), 800);
                                showToast('下载完成', 'success');
                            } else if (result === 'cancelled') {
                                showToast('已取消下载', 'info');
                            }
                        }
                    } catch (err) {
                        if (!silent) {
                            this.activeTask = null;
                            this.closeModal();
                            showToast(err.message || '下载失败', 'error');
                        }
                        throw err;
                    }
                }
            } catch (err) {
                if (!silent) showToast('下载失败', 'error');
            }
        },
    },
});
