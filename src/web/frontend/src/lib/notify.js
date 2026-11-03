/**
 * 轻量 toast 总线：lib 层（api.js 等）与组件层共用，渲染由 ToastStack 组件完成。
 */

let renderer = null;

export function setToastRenderer(fn) {
    renderer = fn;
}

export function showToast(message, type = 'info') {
    if (renderer) renderer(message, type);
    else console.log('[toast]', type, message);
}
