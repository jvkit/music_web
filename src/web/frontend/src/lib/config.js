/**
 * 全局配置与常量
 */

export const API_BASE = 'api';

export const DEFAULT_THUMBNAIL = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' fill='%23e5e7eb'/%3E%3Ccircle cx='32' cy='32' r='16' fill='%239ca3af'/%3E%3C/svg%3E";

export const LS_SETTINGS_KEY = 'musiic_settings';
export const LS_PLAYBACK_STATE_KEY = 'musiic_playback_state';

export const DEFAULT_SETTINGS = {
    targetPlaylistId: 'default',
    limits: {
        youtube: 10,
        netease: 10,
        bilibili: 10,
        soundcloud: 10,
    }
};

export const PLAYBACK_MODES = ['list-loop', 'list-random', 'single-loop'];

export const MODE_LABELS = {
    'list-loop': { icon: 'ph-repeat', title: '列表循环' },
    'list-random': { icon: 'ph-shuffle', title: '列表随机' },
    'single-loop': { icon: 'ph-repeat-once', title: '单曲循环' }
};

/**
 * 获取封面 URL：第三方封面走后端代理，避免跨域/防盗链；无封面则返回默认图。
 */
export function getThumbnailUrl(url) {
    if (!url) return DEFAULT_THUMBNAIL;
    if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('/')) return url;
    return `${API_BASE}/thumbnail?url=${encodeURIComponent(url)}`;
}
