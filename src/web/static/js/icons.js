/**
 * 图标统一入口
 *
 * 项目使用 Phosphor Icons（通过 npm 安装 @phosphor-icons/web）。
 * 所有图标均通过本模块引用，避免在业务代码中直接写 emoji 或图标类名，
 * 方便后续统一替换/升级图标库。
 */

/**
 * Phosphor 图标类名映射。
 * 常规图标使用 `ph ph-<name>`，填充图标使用 `ph-fill ph-<name>`。
 */
export const ICON_CLASS = {
    play: 'ph-play',
    pause: 'ph-pause',
    prev: 'ph-skip-back',
    next: 'ph-skip-forward',

    search: 'ph-magnifying-glass',
    playlist: 'ph-music-notes',
    local: 'ph-hard-drives',
    settings: 'ph-gear',

    music: 'ph-music-note',
    headphones: 'ph-headphones',
    microphone: 'ph-microphone',
    film: 'ph-film-strip',

    heart: 'ph-heart',
    heartFill: 'ph-heart',
    plus: 'ph-plus',
    check: 'ph-check',
    close: 'ph-x',
    trash: 'ph-trash',
    download: 'ph-download-simple',
    copy: 'ph-copy',

    repeat: 'ph-repeat',
    repeatOnce: 'ph-repeat-once',
    shuffle: 'ph-shuffle',

    list: 'ph-list',
    spinner: 'ph-spinner',
    clock: 'ph-clock',
    chart: 'ph-chart-bar',
    disc: 'ph-disc',
};

/**
 * 渲染一个图标 HTML。
 *
 * @param {string} name - ICON_CLASS 中的 key
 * @param {object} options
 * @param {boolean} options.filled - 是否使用填充版本（仅部分图标有 fill 样式）
 * @param {string} options.className - 额外的 CSS class
 * @returns {string}
 */
export function icon(name, { filled = false, className = '' } = {}) {
    const family = filled ? 'ph-fill' : 'ph';
    const cls = [family, ICON_CLASS[name], className].filter(Boolean).join(' ');
    return `<i class="${cls}" aria-hidden="true"></i>`;
}
