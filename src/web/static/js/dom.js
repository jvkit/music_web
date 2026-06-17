/**
 * DOM 元素缓存
 */

export const els = {};

export function cacheElements() {
    const ids = [
        'sourceChips', 'searchInput', 'searchBtn', 'sourceSelect',
        'batchBar', 'selectAll', 'selectedCount', 'copyToPlaylistBtn',
        'tabNav', 'searchView', 'playlistsView', 'localView', 'settingsView',
        'searchLoading', 'searchEmpty', 'searchResults',
        'playlistsSidebar', 'playlistTracks', 'currentPlaylistTitle', 'deletePlaylistBtn', 'createPlaylistBtn',
        'localLoading', 'localList',
        'copyModal', 'copyModalList', 'copyModalCancel',
        'videoModal', 'videoPlayer', 'videoTitle', 'videoModalClose',
        'lyricsModal', 'lyricsModalClose', 'lyricsTitle', 'lyricsArtist', 'lyricsBackground',
        'lyricsScroller', 'lyricsContainer',
        'lyricsPrevBtn', 'lyricsPlayPauseBtn', 'lyricsNextBtn', 'lyricsModeBtn', 'lyricsFavoriteBtn', 'lyricsRemoveBtn',
        'playerBar', 'playerThumbnail', 'playerTitle', 'playerArtist',
        'playPauseBtn', 'prevBtn', 'nextBtn', 'modeBtn', 'playerFavoriteBtn', 'playerLyricsBtn', 'playerRemoveBtn',
        'audioPlayer', 'progressContainer', 'progressBar',
        'currentTime', 'duration', 'toast',
        'downloadModal', 'downloadModalTitle', 'downloadModalStatus', 'downloadModalProgress', 'downloadModalCancel',
        'settingsTargetPlaylist', 'settingsWebFavoritePlaylist', 'settingsLimitYoutube', 'settingsLimitNetease', 'settingsLimitBilibili', 'settingsLimitSoundcloud', 'settingsSaveBtn'
    ];
    ids.forEach(id => els[id] = document.getElementById(id));
}
