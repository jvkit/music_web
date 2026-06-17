/**
 * 设置视图
 */

import { DEFAULT_SETTINGS, LS_SETTINGS_KEY } from '../config.js';
import { els } from '../dom.js';
import { state } from '../state.js';
import { saveToStorage, showToast } from '../utils.js';
import { requireAdminPassword } from '../passwordGate.js';
import { renderSearchResults } from './search.js';

function populatePlaylistSelects() {
    const selects = [els.settingsTargetPlaylist, els.settingsWebFavoritePlaylist];
    const options = state.playlists.filter(p => !p.is_system).map(p => `<option value="${p.id}">${p.name}</option>`).join('');
    selects.forEach(select => {
        if (!select) return;
        const current = select.value;
        select.innerHTML = options;
        if (current && Array.from(select.options).some(o => o.value === current)) {
            select.value = current;
        }
    });
}

export async function saveSettingsFromUI() {
    const ok = await requireAdminPassword('保存设置');
    if (!ok) return;

    const limits = {
        youtube: parseInt(els.settingsLimitYoutube.value, 10) || DEFAULT_SETTINGS.limits.youtube,
        netease: parseInt(els.settingsLimitNetease.value, 10) || DEFAULT_SETTINGS.limits.netease,
        bilibili: parseInt(els.settingsLimitBilibili.value, 10) || DEFAULT_SETTINGS.limits.bilibili,
        soundcloud: parseInt(els.settingsLimitSoundcloud.value, 10) || DEFAULT_SETTINGS.limits.soundcloud,
    };
    Object.keys(limits).forEach(k => {
        limits[k] = Math.max(1, Math.min(50, limits[k]));
    });
    state.settings = {
        ...state.settings,
        targetPlaylistId: els.settingsTargetPlaylist.value || 'default',
        webFavoritePlaylistId: els.settingsWebFavoritePlaylist.value || 'web_favorites',
        limits,
    };
    saveToStorage(LS_SETTINGS_KEY, state.settings);
    showToast('设置已保存', 'success');
    if (state.currentTab === 'search') renderSearchResults();
}

export function renderSettings() {
    populatePlaylistSelects();
    if (state.settings.limits) {
        els.settingsLimitYoutube.value = state.settings.limits.youtube;
        els.settingsLimitNetease.value = state.settings.limits.netease;
        els.settingsLimitBilibili.value = state.settings.limits.bilibili;
        els.settingsLimitSoundcloud.value = state.settings.limits.soundcloud;
    }
    if (state.settings.targetPlaylistId) {
        els.settingsTargetPlaylist.value = state.settings.targetPlaylistId;
    }
    if (state.settings.webFavoritePlaylistId) {
        els.settingsWebFavoritePlaylist.value = state.settings.webFavoritePlaylistId;
    }
}
