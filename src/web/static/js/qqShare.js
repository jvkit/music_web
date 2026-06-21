/**
 * 分享辅助：歌词页「分享」按钮复制歌曲短链到剪贴板。
 * QQ 在 HTTP/IP 环境下无法通过 JS API 可靠设置分享卡片，
 * 因此采用「复制链接 → 用户手动粘贴到 QQ」的方案。
 */

function copyText(text, onSuccess, onError) {
    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(onError);
        return;
    }
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
        const ok = document.execCommand('copy');
        document.body.removeChild(textarea);
        ok ? onSuccess() : onError();
    } catch (err) {
        document.body.removeChild(textarea);
        onError();
    }
}

export function shareTrack(track = null) {
    if (typeof window === 'undefined' || !track) return;
    try {
        const url = new URL(window.location.href);
        url.searchParams.delete('share');
        url.searchParams.delete('song');
        const shareUrl = url.toString();
        copyText(
            shareUrl,
            () => alert('分享链接已复制，请粘贴到 QQ 聊天发送'),
            () => alert('复制失败')
        );
    } catch {
        // ignore
    }
}
