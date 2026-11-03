<script setup>
import { onMounted } from 'vue';
import { useDiscoverStore } from '../stores/discover.js';
import TrackCard from '../components/TrackCard.vue';
import { getThumbnailUrl } from '../lib/utils.js';

const discover = useDiscoverStore();

onMounted(() => discover.init());

function fmtCount(n) {
    if (n == null) return '';
    if (n >= 100000000) return `${(n / 100000000).toFixed(1)}亿`;
    if (n >= 10000) return `${Math.round(n / 10000)}万`;
    return String(n);
}
</script>

<template>
    <section class="view">
        <!-- 私人 FM：随手来一首 -->
        <button class="fm-card" @click="discover.playFm()">
            <span class="fm-icon"><i class="ph-fill ph-radio"></i></span>
            <span class="fm-copy">
                <strong>私人 FM</strong>
                <span>随机来一首，看看命运递给你什么歌</span>
            </span>
            <i class="ph ph-caret-right fm-go"></i>
        </button>

        <!-- 官方榜单 -->
        <section class="discover-block">
            <h2 class="block-title"><i class="ph ph-chart-line-up"></i>官方榜单</h2>
            <div v-if="discover.toplistsLoading" class="state-box slim">
                <i class="ph ph-spinner spin"></i><p>加载榜单…</p>
            </div>
            <div v-else-if="discover.toplists.length" class="toplist-row">
                <button
                    v-for="t in discover.toplists"
                    :key="t.id"
                    class="toplist-card"
                    @click="discover.openPlaylist(t.id)"
                >
                    <img :src="getThumbnailUrl(t.cover)" :alt="t.name" loading="lazy" />
                    <span class="toplist-name">{{ t.name }}</span>
                    <span v-if="t.update_frequency" class="toplist-freq">{{ t.update_frequency }}</span>
                </button>
            </div>
        </section>

        <!-- 分类 chips -->
        <section class="discover-block">
            <div class="chips">
                <button
                    v-for="c in discover.categories"
                    :key="c.id"
                    class="chip"
                    :class="{ active: discover.cat === c.id && !discover.current }"
                    @click="discover.selectCat(c.id)"
                >{{ c.name }}</button>
            </div>
        </section>

        <!-- 歌单 / 榜单 / FM 详情 -->
        <div v-if="discover.detailLoading" class="state-box">
            <i class="ph ph-spinner spin"></i><p>打开歌单…</p>
        </div>
        <section v-else-if="discover.current" class="discover-block">
            <header class="detail-head">
                <img class="detail-cover" :src="getThumbnailUrl(discover.current.playlist.cover)" alt="" />
                <div class="detail-meta">
                    <h2>{{ discover.current.playlist.name }}</h2>
                    <p v-if="discover.current.playlist.creator" class="detail-sub">
                        by {{ discover.current.playlist.creator }} · {{ discover.current.tracks.length }} 首
                    </p>
                    <p v-if="discover.current.playlist.description" class="detail-desc">
                        {{ discover.current.playlist.description }}
                    </p>
                    <div class="detail-actions">
                        <button class="btn-soft" @click="discover.playAll()">
                            <i class="ph ph-play"></i> 播放全部
                        </button>
                        <button class="btn-soft" @click="discover.back()">
                            <i class="ph ph-arrow-left"></i> 返回
                        </button>
                    </div>
                </div>
            </header>
            <div>
                <TrackCard
                    v-for="track in discover.current.tracks"
                    :key="track.id"
                    :track="track"
                    :selectable="false"
                    :show-source="false"
                    context="discover"
                />
            </div>
        </section>

        <!-- 歌单墙 -->
        <section v-else class="discover-block">
            <div v-if="discover.wallLoading" class="state-box">
                <i class="ph ph-spinner spin"></i><p>加载歌单…</p>
            </div>
            <div v-else-if="!discover.playlists.length" class="state-box">
                <p>这个分类暂时没有歌单，换一个试试</p>
            </div>
            <div v-else class="playlist-grid">
                <button
                    v-for="p in discover.playlists"
                    :key="p.id"
                    class="playlist-card"
                    @click="discover.openPlaylist(p.id)"
                >
                    <span class="playlist-cover-wrap">
                        <img :src="getThumbnailUrl(p.cover)" :alt="p.name" loading="lazy" />
                        <span v-if="p.play_count" class="playlist-count">
                            <i class="ph ph-play"></i>{{ fmtCount(p.play_count) }}
                        </span>
                    </span>
                    <span class="playlist-name">{{ p.name }}</span>
                    <span v-if="p.track_count" class="playlist-tracks">{{ p.track_count }} 首</span>
                </button>
            </div>
        </section>
    </section>
</template>

<style scoped>
.fm-card {
    display: flex; align-items: center; gap: 14px; width: 100%;
    padding: 14px 18px; border-radius: 12px; text-align: left;
    background: linear-gradient(120deg, rgba(185, 245, 109, .12), rgba(185, 245, 109, .03));
    border: 1px solid rgba(185, 245, 109, .14);
    transition: border-color .15s;
}
.fm-card:hover { border-color: rgba(185, 245, 109, .35); }
.fm-icon { font-size: 24px; color: var(--lime); display: flex; }
.fm-copy { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.fm-copy strong { font-size: 14px; color: #e3e8e1; }
.fm-copy span { font-size: 12px; color: #747c76; }
.fm-go { color: #747c76; }

.discover-block { margin-top: 22px; }
.block-title { font-size: 13px; color: #aab2ac; margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }
.block-title i { color: var(--lime); }

.toplist-row { display: flex; gap: 10px; overflow-x: auto; padding-bottom: 6px; }
.toplist-card {
    flex: 0 0 auto; display: flex; flex-direction: column; align-items: center; gap: 6px;
    width: 92px; padding: 8px 4px; border-radius: 10px; border: 1px solid transparent;
    transition: border-color .15s;
}
.toplist-card:hover { border-color: #3d4d35; }
.toplist-card img { width: 76px; height: 76px; border-radius: 8px; object-fit: cover; }
.toplist-name { font-size: 12px; color: #e3e8e1; max-width: 84px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.toplist-freq { font-size: 10px; color: #747c76; }

.playlist-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 14px; }
.playlist-card {
    display: flex; flex-direction: column; align-items: flex-start; gap: 6px; text-align: left;
    padding: 0; border: none; border-radius: 10px;
}
.playlist-cover-wrap { position: relative; width: 100%; }
.playlist-card img { width: 100%; aspect-ratio: 1; border-radius: 10px; object-fit: cover; border: 1px solid rgba(255, 255, 255, .06); }
.playlist-count {
    position: absolute; right: 6px; top: 6px; display: flex; align-items: center; gap: 3px;
    font-size: 11px; color: #e3e8e1; padding: 2px 7px; border-radius: 999px;
    background: rgba(0, 0, 0, .55);
}
.playlist-count i { font-size: 11px; }
.playlist-name {
    font-size: 12px; color: #c4cbc2; line-height: 1.4;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.playlist-tracks { font-size: 11px; color: #747c76; }

.detail-head { display: flex; gap: 16px; margin-bottom: 14px; align-items: flex-start; }
.detail-cover { width: 104px; height: 104px; border-radius: 12px; object-fit: cover; border: 1px solid rgba(255, 255, 255, .06); }
.detail-meta { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.detail-meta h2 { font-size: 17px; color: #e3e8e1; }
.detail-sub { font-size: 12px; color: #747c76; }
.detail-desc { font-size: 12px; color: #8d958f; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.detail-actions { display: flex; gap: 8px; margin-top: 4px; }
.detail-actions .btn-soft { display: inline-flex; align-items: center; gap: 5px; }

.state-box.slim { padding: 28px 20px; }

@media (max-width: 640px) {
    .detail-head { flex-direction: column; }
    .toplist-card { width: 84px; }
    .toplist-card img { width: 68px; height: 68px; }
}
</style>
