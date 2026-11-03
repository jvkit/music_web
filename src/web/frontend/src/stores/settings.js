/**
 * 用户设置（收藏目标、搜索分页数量）
 */

import { defineStore } from 'pinia';
import { DEFAULT_SETTINGS, LS_SETTINGS_KEY } from '../lib/config.js';
import { loadFromStorage, saveToStorage } from '../lib/utils.js';

function loadSettings() {
    const saved = loadFromStorage(LS_SETTINGS_KEY, {});
    return {
        ...DEFAULT_SETTINGS,
        ...saved,
        limits: { ...DEFAULT_SETTINGS.limits, ...(saved.limits || {}) }
    };
}

export const useSettingsStore = defineStore('settings', {
    state: () => ({
        settings: loadSettings(),
    }),
    actions: {
        save(payload) {
            this.settings = { ...this.settings, ...payload };
            saveToStorage(LS_SETTINGS_KEY, this.settings);
        },
        limitFor(source) {
            return this.settings.limits[source] || 10;
        },
    },
});
