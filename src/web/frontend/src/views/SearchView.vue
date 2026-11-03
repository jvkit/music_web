<script setup>
import { computed, ref, onMounted, nextTick } from 'vue';
import { useSearchStore } from '../stores/search.js';
import { useServerLibraryStore } from '../stores/serverLibrary.js';
import { useSourcesStore } from '../stores/sources.js';
import { useUiStore } from '../stores/ui.js';
import { filterByMediaType } from '../lib/utils.js';
import TrackCard from '../components/TrackCard.vue';
import Chips from '../components/Chips.vue';

const search = useSearchStore();
const serverLibrary = useServerLibraryStore();
const sources = useSourcesStore();
const ui = useUiStore();

const searchInput = ref(null);
const resultsEl = ref(null);

const SOURCE_GROUPS = [
    { id: 'recommended', name: '强烈推荐', sources: ['web_liumingye'] },
    { id: 'stable', name: '稳定源', sources: ['netease', 'bilibili', 'web_gequbao', 'web_fangpi'] },
    { id: 'direct', name: '直连源（可播性一般）', sources: ['web_jbsou', 'web_netease_fe_mm'] },
    { id: 'unstable', name: '不稳定 / 备选', sources: ['web_qqmp3', 'web_musicenc', 'web_tonzhon', 'web_tonzhon_whamon'] },
    { id: 'foreign', name: '外网源', sources: ['youtube', 'soundcloud'] },
];

const NATIVE_SOURCE_NAMES = {
    youtube: 'YouTube',
    netease: '网易云',
    bilibili: 'Bilibili',
    soundcloud: 'SoundCloud',
};

const groups = computed(() => {
    const hidden = new Set(sources.hiddenSources || []);
    return SOURCE_GROUPS.map(group => {
        const opts = group.sources
            .filter(id => !hidden.has(id))
            .filter(id => id.startsWith('web_') ? sources.webSources.some(s => s.id === id) : true)
            .map(id => ({
                id,
                name: sourceName(id),
            }));
        return { name: group.name, opts };
    }).filter(g => g.opts.length > 0);
});

function sourceName(sourceId) {
    if (NATIVE_SOURCE_NAMES[sourceId]) return NATIVE_SOURCE_NAMES[sourceId];
    const ws = sources.webSources.find(s => s.id === sourceId);
    if (!ws) return sourceId;
    let name = ws.display_name;
    if (ws.direct_stream) name += ' ⭐';
    if (ws.status === 'unstable') name += '（不稳定）';
    return name;
}

const filteredResults = computed(() => filterByMediaType(search.results, search.mediaTypeFilter));
const filteredServerItems = computed(() => filterByMediaType(serverLibrary.items, serverLibrary.mediaTypeFilter));

async function doSearch() {
    await search.doSearch();
    await nextTick();
    resultsEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function onInput() {
    if (!search.input.trim() && search.query) {
        search.clearResults();
    }
}

onMounted(() => {
    ui.currentTab = 'search';
    if (!serverLibrary.loaded) serverLibrary.load();
    requestAnimationFrame(() => searchInput.value?.focus({ preventScroll: true }));
});
</script>

<template>
    <section class="view">
        <section class="search-panel">
            <div class="search">
                <span class="search-icon"><i class="ph ph-magnifying-glass"></i></span>
                <input
                    id="searchInput"
                    ref="searchInput"
                    v-model="search.input"
                    type="text"
                    placeholder="搜索歌曲、艺人、专辑…"
                    aria-label="搜索歌曲"
                    :disabled="search.isSearching"
                    @keydown.enter="doSearch"
                    @input="onInput"
                >
                <kbd>⌘ K</kbd>
            </div>
            <select v-model="search.source" class="source">
                <template v-for="group in groups" :key="group.name">
                    <optgroup :label="group.name">
                        <option v-for="opt in group.opts" :key="opt.id" :value="opt.id">{{ opt.name }}</option>
                    </optgroup>
                </template>
            </select>
            <button class="search-btn" :disabled="search.isSearching" @click="doSearch">搜索</button>
        </section>

        <!-- 服务器音乐库（无搜索词时展示） -->
        <section v-if="!search.query" class="results">
            <header class="results-head">
                <div class="results-title">
                    <h2>服务器音乐库</h2>
                    <span>所有用户共享 · 去重后 {{ serverLibrary.items.length }} 首</span>
                </div>
                <div class="filter-row">
                    <Chips v-model="serverLibrary.mediaTypeFilter" />
                    <span class="view-count">{{ filteredServerItems.length ? `${filteredServerItems.length} 首` : '' }}</span>
                </div>
            </header>
            <div v-if="serverLibrary.loading" class="state-box">
                <i class="ph ph-spinner spin"></i>
                <p>加载音乐库…</p>
            </div>
            <div v-else-if="serverLibrary.loadFailed" class="state-box"><p>服务器音乐库加载失败</p></div>
            <div v-else-if="filteredServerItems.length === 0" class="state-box"><p>服务器音乐库还是空的</p></div>
            <div v-else>
                <TrackCard
                    v-for="track in filteredServerItems"
                    :key="track.id"
                    :track="track"
                    :selectable="false"
                    :show-source="true"
                    context="server"
                />
            </div>
        </section>

        <!-- 搜索结果 -->
        <section v-else ref="resultsEl" class="results">
            <header class="results-head">
                <div class="results-title">
                    <h2>搜索结果</h2>
                    <span>“{{ search.query }}” · 找到 {{ search.results.length }} 首</span>
                </div>
                <div class="filter-row">
                    <Chips v-model="search.mediaTypeFilter" />
                    <span class="view-count">{{ filteredResults.length ? `按相关度 · ${filteredResults.length} 首` : '' }}</span>
                </div>
            </header>

            <div v-if="search.isSearching" class="state-box">
                <i class="ph ph-spinner spin"></i>
                <p>搜索中…</p>
            </div>
            <template v-else>
                <div v-if="filteredResults.length === 0" class="state-box"><p>暂无搜索结果，换个关键词试试</p></div>
                <div v-else>
                    <TrackCard
                        v-for="track in filteredResults"
                        :key="track.id"
                        :track="track"
                        :selectable="true"
                        :show-source="true"
                        context="search"
                    />
                    <div v-if="search.hasMore" class="load-more-wrap">
                        <button class="btn-soft" :disabled="search.isLoadingMore" @click="search.loadMore()">
                            {{ search.isLoadingMore ? '加载中…' : '加载更多' }}
                        </button>
                    </div>
                </div>
            </template>
        </section>
    </section>
</template>
