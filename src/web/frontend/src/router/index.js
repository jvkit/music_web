/**
 * 路由：hash 模式（FastAPI 静态挂载无需 SPA 回退，任意前缀可用）
 *
 * /admin 不在主页导航出现，仅通过后端 /admin 路径或 #/admin 直达。
 */

import { createRouter, createWebHashHistory } from 'vue-router';
import SearchView from '../views/SearchView.vue';
import PlaylistsView from '../views/PlaylistsView.vue';
import LocalView from '../views/LocalView.vue';
import SettingsView from '../views/SettingsView.vue';
import AdminView from '../views/AdminView.vue';

const router = createRouter({
    history: createWebHashHistory(),
    routes: [
        { path: '/', name: 'search', component: SearchView, meta: { title: '发现你的下一首歌', sub: '从熟悉的旋律出发，也多走一点陌生的路。' } },
        { path: '/playlists', name: 'playlists', component: PlaylistsView, meta: { title: '我的列表', sub: '收藏、歌单与网页收藏都在这里。' } },
        { path: '/local', name: 'local', component: LocalView, meta: { title: '本地音乐', sub: '已经下载到服务器的歌曲。' } },
        { path: '/settings', name: 'settings', component: SettingsView, meta: { title: '设置', sub: '搜索数量、收藏目标与网页音源。' } },
        { path: '/admin', name: 'admin', component: AdminView, meta: { title: '后台管理', sub: '数据管控中心', standalone: true } },
        { path: '/:pathMatch(.*)*', redirect: '/' },
    ],
});

export default router;
