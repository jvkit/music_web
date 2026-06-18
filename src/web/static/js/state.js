/**
 * 全局状态
 */

import { DEFAULT_SETTINGS } from './config.js';

export const state = {
    currentTab: 'search',
    searchResults: [],
    searchQuery: '',
    searchSource: 'web_liumingye',
    searchOffset: 0,
    searchHasMore: true,
    webSources: [],
    hiddenSources: [],
    selectedIds: new Set(),
    currentTrack: null,
    isPlaying: false,

    // 播放列表
    playlists: [],
    currentPlaylistId: 'default',

    // 设置
    settings: { ...DEFAULT_SETTINGS },

    // 本地
    localItems: [],

    // 音乐库歌曲缓存（song_id -> song）
    librarySongs: {},

    // 媒体类型筛选：all | audio | video
    mediaTypeFilter: {
        search: 'all',
        playlist: 'all',
        local: 'all',
    },

    // 播放器队列与模式
    queue: [],
    queueIndex: -1,
    playbackMode: 'list-loop',
    randomHistory: [],

    // 复制弹窗
    copyModalOpen: false,

    // 当前下载任务
    activeDownload: null,

    // 当前曲目是否已记录播放频率
    playRecordedForTrackId: null,

    // 收听频率统计 track_id -> count
    playCounts: {},

    // 当前歌词数据
    lyrics: [],
    lyricsSource: null,

    // 边下边播回退状态
    streamFallback: null,

    // 当前正在加载（防重复点击）的曲目 ID
    loadingTrackId: null,

    // 是否正在搜索（防重复提交）
    isSearching: false,

    // 一起听歌房间
    room: {
        id: null,
        connected: false,
        participants: [],
        isInRoom: false,
        syncEnabled: false,
        currentTrack: null,
        isPlaying: false,
        position: 0,
        updatedAt: 0,
        queue: [],
    },
};
