/**
 * 精灵动画引擎（框架无关）：帧循环 + 情绪切换
 *
 * 素材来自后端 /api/sprite/*（pet_content 的 boy/小河灵，webp 帧序列）。
 * 情绪（mood）映射到 manifest 的 clip：idle=stand 循环、music=听歌循环、
 * happy/think 单次播完回到原情绪。
 */

import { API_BASE } from './config.js';

export function createSpriteAnim() {
    let manifest = null;
    let loadingPromise = null;
    let timer = null;
    let currentClip = null;
    let currentFrame = 0;
    let mood = 'idle';
    let playingOnce = false;
    let onFrame = null;
    const preloaded = new Set();

    const frameUrl = (clip, i) => `${API_BASE}/sprite/frame?act=${clip.act}&i=${i}`;

    const preloadClip = (name) => {
        const clip = manifest?.clips?.[name];
        if (!clip) return;
        for (let i = clip.start; i <= clip.end; i++) {
            const url = frameUrl(clip, i);
            if (preloaded.has(url)) continue;
            preloaded.add(url);
            const img = new Image();
            img.src = url;
        }
    };

    const tick = () => {
        if (!currentClip) return;
        const { start, end } = currentClip;
        currentFrame += 1;
        if (currentFrame > end) {
            if (playingOnce) {
                // 单次动作播完：回到当前情绪的循环
                playingOnce = false;
                playMood(mood);
                return;
            }
            currentFrame = start;
        }
        if (onFrame) onFrame(frameUrl(currentClip, currentFrame));
    };

    const playClip = (name, { once = false } = {}) => {
        const clip = manifest?.clips?.[name];
        if (!clip) return false;
        if (timer) clearInterval(timer);
        currentClip = clip;
        currentFrame = clip.start;
        playingOnce = once;
        if (onFrame) onFrame(frameUrl(currentClip, currentFrame));
        const fps = clip.fps || manifest?.fps || 12;
        timer = setInterval(tick, 1000 / fps);
        preloadClip(name);
        return true;
    };

    const playMood = (m) => {
        if (m === 'music') return playClip('music');
        return playClip('stand');
    };

    return {
        /** 加载 manifest 并进入 idle 待机循环 */
        async start() {
            if (!loadingPromise) {
                loadingPromise = fetch(`${API_BASE}/sprite/manifest`)
                    .then((r) => r.json())
                    .then((data) => {
                        if (!data.available) return false;
                        manifest = data;
                        preloadClip('stand');
                        preloadClip('music');
                        playMood(mood);
                        return true;
                    })
                    .catch(() => false);
            }
            return loadingPromise;
        },
        onFrame(cb) { onFrame = cb; },
        /** idle=待机 / music=听歌摇摆 / happy=开心(单次) / think=思考(单次弹跳) */
        setMood(m) {
            if (!manifest) { mood = m; return; }
            if (m === 'happy') { playClip('heart', { once: true }); return; }
            if (m === 'think') { playClip('bounce', { once: true }); return; }
            mood = m;
            if (!playingOnce) playMood(m);
        },
        stop() { if (timer) clearInterval(timer); timer = null; },
    };
}
