/**
 * 手机 QQ 内置浏览器分享卡片定制
 * 文档：
 *   - https://open.mobile.qq.com/api/mqq/index#data.setShareInfo
 *   - https://open.mobile.qq.com/api/common/index#ui.setOnShareHandler
 */

const DEBUG = /music[4-6]/.test(window.location.pathname) || new URLSearchParams(window.location.search).has('qqdebug');

function log(...args) {
    console.log('[QQShare]', ...args);
    if (DEBUG) renderDebug(args.join(' '));
}

function renderDebug(text) {
    let box = document.getElementById('qq-share-debug');
    if (!box) {
        box = document.createElement('div');
        box.id = 'qq-share-debug';
        box.style.cssText = 'position:fixed;bottom:10px;left:10px;right:10px;max-height:150px;overflow:auto;background:rgba(0,0,0,0.8);color:#0f0;font-size:12px;padding:8px;z-index:99999;border-radius:6px;';
        document.body.appendChild(box);
    }
    const line = document.createElement('div');
    line.textContent = `${new Date().toLocaleTimeString()} ${text}`;
    box.appendChild(line);
}

function getBaseUrl() {
    return window.location.href.replace(/\/[^/]*$/, '/');
}

function toAbsoluteUrl(url) {
    if (!url) return null;
    if (/^(https?:|data:|blob:)/i.test(url)) return url;
    try {
        return new URL(url, getBaseUrl()).href;
    } catch {
        return null;
    }
}

function getAppIconUrl() {
    return toAbsoluteUrl('icons/icon-512.png');
}

function getShareCode() {
    try {
        return new URL(window.location.href).searchParams.get('c');
    } catch {
        return null;
    }
}

function getStrategy() {
    const path = window.location.pathname;
    if (path.includes('/music5')) return 'meta-only';
    if (path.includes('/music6')) return 'on-share-handler';
    return 'default'; // music4 或主站：全部尝试
}

function pickImageUrl(track) {
    const code = getShareCode();
    if (code) {
        return toAbsoluteUrl(`api/share_image?code=${encodeURIComponent(code)}`);
    }
    return toAbsoluteUrl(track?.thumbnail || track?.cover_url) || getAppIconUrl();
}

function buildShareInfo(track = null) {
    const title = track
        ? `${track.title} - ${track.artist || '未知歌手'}`
        : '音河 - 在线音乐';
    const desc = track
        ? `在音河收听《${track.title}》`
        : '在线音乐搜索、试听与分享';
    const image_url = pickImageUrl(track);
    const share_url = window.location.href;
    const info = { title, desc, image_url };
    if (share_url.length <= 120) {
        info.share_url = share_url;
    }
    return info;
}

function callSetShareInfo(info) {
    if (!window.mqq) return false;
    try {
        if (window.mqq.data && typeof window.mqq.data.setShareInfo === 'function') {
            window.mqq.data.setShareInfo(info);
            log('mqq.data.setShareInfo OK', JSON.stringify(info));
            return true;
        }
        if (typeof window.mqq.invoke === 'function') {
            window.mqq.invoke('data', 'setShareInfo', info);
            log('mqq.invoke OK', JSON.stringify(info));
            return true;
        }
    } catch (err) {
        log('setShareInfo error:', err.message);
    }
    return false;
}

function callOnShareHandler(info) {
    if (!window.mqq || !window.mqq.ui) return false;
    try {
        if (typeof window.mqq.ui.setOnShareHandler !== 'function') return false;
        window.mqq.ui.setOnShareHandler(function (type) {
            log('setOnShareHandler triggered, type=' + type);
            window.mqq.ui.shareMessage({
                title: info.title,
                desc: info.desc,
                share_type: type,
                share_url: info.share_url || window.location.href,
                image_url: info.image_url,
                back: true,
            }, function (result) {
                log('shareMessage callback:', JSON.stringify(result));
            });
        });
        log('mqq.ui.setOnShareHandler OK');
        return true;
    } catch (err) {
        log('setOnShareHandler error:', err.message);
    }
    return false;
}

function loadQQApi() {
    return new Promise((resolve) => {
        if (window.mqq) return resolve();
        const script = document.createElement('script');
        script.src = 'https://open.mobile.qq.com/sdk/qqapi.js';
        script.async = true;
        script.onload = () => { log('qqapi.js loaded'); resolve(); };
        script.onerror = () => { log('qqapi.js load failed'); resolve(); };
        document.head.appendChild(script);
        setTimeout(resolve, 2000);
    });
}

async function doUpdate(track = null) {
    if (typeof window === 'undefined') return false;

    const ua = navigator.userAgent || '';
    const isQQ = /QQ\//.test(ua);
    const isQZ = /Qzone\//.test(ua);
    if (!isQQ && !isQZ) {
        log('not QQ/Qzone, skip');
        return false;
    }

    await loadQQApi();

    const mqq = window.mqq;
    log('mqq present:', !!mqq, 'invoke:', !!(mqq && mqq.invoke), 'data:', !!(mqq && mqq.data), 'ui:', !!(mqq && mqq.ui));

    const info = buildShareInfo(track);
    log('share info:', JSON.stringify(info));

    const strategy = getStrategy();
    log('strategy:', strategy);

    if (strategy === 'meta-only') {
        log('meta-only strategy: rely on server meta tags');
        return true;
    }

    if (strategy === 'on-share-handler') {
        return callOnShareHandler(info);
    }

    // default: try both
    const ok1 = callSetShareInfo(info);
    const ok2 = callOnShareHandler(info);
    return ok1 || ok2;
}

export function updateQQShare(track = null) {
    doUpdate(track);
}
