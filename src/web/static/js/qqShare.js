/**
 * 手机 QQ 内置浏览器分享卡片定制
 * 文档：https://open.mobile.qq.com/api/mqq/index#data.setShareInfo
 */

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

function pickImageUrl(track) {
    // 优先用歌曲封面；解析失败/不存在则用 App 图标，绝不用 data URI（QQ 不认）
    return toAbsoluteUrl(track?.thumbnail || track?.cover_url) || getAppIconUrl();
}

function doUpdate(track = null) {
    const mqq = window.mqq;
    if (!mqq || typeof mqq.invoke !== 'function') return false;

    try {
        const title = track
            ? `${track.title} - ${track.artist || '未知歌手'}`
            : '音河 - 在线音乐';
        const desc = track
            ? `在音河收听《${track.title}》`
            : '在线音乐搜索、试听与分享';
        const image_url = pickImageUrl(track);

        const params = {
            title,
            desc,
            image_url,
        };
        // share_url 限制 120 字节，超长时不传，让 QQ 用当前页面 URL
        const shareUrl = window.location.href;
        if (shareUrl.length <= 120) {
            params.share_url = shareUrl;
        }
        mqq.invoke('data', 'setShareInfo', params);
        return true;
    } catch (err) {
        console.error('QQ setShareInfo 失败:', err);
        return false;
    }
}

export function updateQQShare(track = null) {
    if (typeof window === 'undefined') return;

    // 立即试一次
    if (doUpdate(track)) return;

    // mqq 可能还没注入，最多重试 3 次
    let attempts = 0;
    const timer = setInterval(() => {
        attempts += 1;
        if (doUpdate(track) || attempts >= 3) {
            clearInterval(timer);
        }
    }, 800);
}
