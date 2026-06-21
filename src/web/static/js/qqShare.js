/**
 * 手机 QQ 内置浏览器分享卡片定制
 * 文档：https://open.mobile.qq.com/api/mqq/index#data.setShareInfo
 */

import { DEFAULT_THUMBNAIL } from './config.js';

function toAbsoluteUrl(url) {
    if (!url) return DEFAULT_THUMBNAIL;
    if (/^(https?:|data:|blob:)/i.test(url)) return url;
    // 相对路径：基于当前页面目录拼接
    const base = window.location.href.replace(/\/[^/]*$/, '/');
    try {
        return new URL(url, base).href;
    } catch {
        return DEFAULT_THUMBNAIL;
    }
}

export function updateQQShare(track = null) {
    if (typeof window === 'undefined') return;
    const mqq = window.mqq;
    if (!mqq || typeof mqq.invoke !== 'function') return;

    try {
        const title = track
            ? `${track.title} - ${track.artist || '未知歌手'}`
            : '音河 - 在线音乐';
        const desc = track
            ? `在音河收听《${track.title}》`
            : '在线音乐搜索、试听与分享';
        const image_url = toAbsoluteUrl(track?.thumbnail || track?.cover_url);

        // share_url 不自定义，让 QQ 使用当前页面 URL（自定义需同域且<=120字节，容易踩坑）
        mqq.invoke('data', 'setShareInfo', {
            title,
            desc,
            image_url,
        });
    } catch (err) {
        console.error('QQ setShareInfo 失败:', err);
    }
}
