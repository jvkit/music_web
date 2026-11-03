/**
 * 听歌识曲状态：录音（麦克风/系统声音）→ 上传 /api/recognize → 结果列表
 *
 * 指纹窗口为录音的第 4-10 秒（后端固定），故至少录 11 秒留余量。
 */

import { defineStore } from 'pinia';
import { recognizeUpload } from '../lib/api.js';
import { showToast } from '../lib/notify.js';

const RECORD_SECONDS = 11;

export const useRecognizeStore = defineStore('recognize', {
    state: () => ({
        modalOpen: false,
        mode: null,          // 'mic' | 'system'
        phase: 'idle',       // idle | recording | uploading | done
        elapsed: 0,
        results: [],
        error: '',
        _stream: null,
        _recorder: null,
        _tick: null,
    }),

    actions: {
        open() {
            this.cancel();
            // 保留上一次的识别结果：关掉弹窗后再打开还能继续挑其它版本
            if (this.phase !== 'done') {
                this.phase = 'idle';
                this.results = [];
                this.error = '';
                this.mode = null;
                this.elapsed = 0;
            }
            this.modalOpen = true;
        },

        close() {
            this.cancel();
            this.modalOpen = false;
        },

        reset() {
            this.cancel();
            this.phase = 'idle';
            this.results = [];
            this.error = '';
            this.mode = null;
            this.elapsed = 0;
        },

        cancel() {
            if (this._tick) { clearInterval(this._tick); this._tick = null; }
            if (this._recorder && this._recorder.state !== 'inactive') this._recorder.stop();
            this._recorder = null;
            if (this._stream) {
                this._stream.getTracks().forEach((t) => t.stop());
                this._stream = null;
            }
            if (this.phase === 'recording') this.phase = 'idle';
        },

        async start(mode, { silent = false } = {}) {
            this.cancel();
            this.mode = mode;
            this.error = '';
            this.results = [];

            // 非安全上下文（http + 非 localhost）下浏览器禁止录音/录屏，且不给弹窗
            if (!window.isSecureContext) {
                this.error = '当前是 HTTP 页面，浏览器禁止录音和录屏。请用 https 域名访问（或 localhost）后再试。';
                return;
            }
            if (!navigator.mediaDevices) {
                this.error = '此浏览器不支持媒体采集，请使用新版 Chrome / Edge。';
                return;
            }
            if (mode === 'system' && typeof navigator.mediaDevices.getDisplayMedia !== 'function') {
                this.error = '此浏览器不支持录制系统声音（getDisplayMedia），请使用新版 Chrome / Edge。';
                return;
            }

            try {
                this._stream = mode === 'system'
                    ? await navigator.mediaDevices.getDisplayMedia({ video: true, audio: true })
                    : await navigator.mediaDevices.getUserMedia({
                        audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false },
                    });
            } catch (err) {
                console.warn('识曲取流失败:', err);
                this.error = this.describeMediaError(err, mode);
                return;
            }

            if (this._stream.getAudioTracks().length === 0) {
                this.cancel();
                this.error = '没有捕获到系统声音：在选择框里请勾选「分享标签页音频 / 系统音频」后重试';
                return;
            }

            const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
                ? 'audio/webm;codecs=opus'
                : (MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4');
            const chunks = [];

            // 关键：录屏流是 video+audio 双轨，直接喂给 audio-only 的 MediaRecorder 会抛
            // NotSupportedError。这里只抽音轨重新组流。
            const recordStream = new MediaStream(this._stream.getAudioTracks());
            let recorder;
            try {
                recorder = new MediaRecorder(recordStream, { mimeType });
            } catch (err) {
                console.error('MediaRecorder 初始化失败:', err);
                this.cancel();
                this.error = `录音初始化失败（${err.name || err.message}）`;
                return;
            }
            this._recorder = recorder;

            recorder.onerror = (event) => {
                console.error('MediaRecorder 错误:', event.error);
                this.cancel();
                this.error = `录音出错（${(event.error && event.error.name) || '未知'}）`;
            };

            recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
            recorder.onstop = async () => {
                if (this._stream) {
                    this._stream.getTracks().forEach((t) => t.stop());
                    this._stream = null;
                }
                if (this.phase !== 'recording') return; // 已取消
                this.phase = 'uploading';
                try {
                    const blob = new Blob(chunks, { type: mimeType });
                    const fmt = mimeType.includes('mp4') ? 'm4a' : 'webm';
                    const data = await recognizeUpload(blob, fmt);
                    this.results = data.tracks || [];
                    this.phase = 'done';
                    if (!this.results.length) {
                        this.error = '没听出来这段音频，换个段落、离音源近一点再试试';
                    } else if (!silent) {
                        showToast(`识别成功：${this.results[0].title}`, 'success');
                    }
                } catch (err) {
                    console.error('识曲失败:', err);
                    this.error = '识别失败，请稍后再试';
                    this.phase = 'done';
                }
            };

            try {
                recorder.start(500);
            } catch (err) {
                console.error('录音启动失败:', err);
                this.cancel();
                this.error = `录音启动失败（${err.name || err.message}）`;
                return;
            }
            this.phase = 'recording';
            this.elapsed = 0;
            this._tick = setInterval(() => {
                this.elapsed = Math.min(this.elapsed + 0.1, RECORD_SECONDS);
                if (this.elapsed >= RECORD_SECONDS) this.stop();
            }, 100);
        },

        stop() {
            if (this._tick) { clearInterval(this._tick); this._tick = null; }
            if (this._recorder && this._recorder.state === 'recording') this._recorder.stop();
        },

        /** 把 DOMException 翻译成可读提示（带错误名，方便排查） */
        describeMediaError(err, mode) {
            const name = (err && err.name) || '未知错误';
            const detail = (err && err.message) || '';
            if (name === 'NotAllowedError') {
                return mode === 'system'
                    ? '共享请求被取消或被浏览器拒绝（也可能被安全策略禁止了 display-capture）'
                    : '麦克风权限被拒绝，请在地址栏站点设置里允许麦克风';
            }
            if (name === 'NotFoundError' || name === 'OverconstrainedError') {
                return mode === 'system' ? '这台设备没有可共享的音源' : '没有找到麦克风设备';
            }
            if (name === 'NotReadableError') {
                return '录音设备被其他应用占用，关掉占用它的程序再试';
            }
            if (name === 'AbortError') {
                return '共享被中断，请重新点一次试试';
            }
            if (name === 'TypeError' || name === 'NotSupportedError') {
                return '浏览器不支持该采集方式，请改用新版 Chrome / Edge';
            }
            return `未能开始捕获（${name}${detail ? '：' + detail : ''}）`;
        },
    },
});
