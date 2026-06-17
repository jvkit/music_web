/**
 * 一起听歌房间 UI：按钮、弹窗、顶部横幅
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { icon } from '../icons.js';
import { showToast } from '../utils.js';
import {
    isInRoom,
    getRoomId,
    createRoom,
    connectRoom,
    leaveRoom,
    checkRoomExists,
} from '../room.js';

export function initRoomUI() {
    if (!els.roomBtn) return;

    els.roomBtn.addEventListener('click', toggleRoomModal);
    if (els.roomModalClose) els.roomModalClose.addEventListener('click', closeRoomModal);
    if (els.roomModal) {
        els.roomModal.addEventListener('click', e => {
            if (e.target === els.roomModal) closeRoomModal();
        });
    }
    if (els.roomCreateBtn) els.roomCreateBtn.addEventListener('click', handleCreateRoom);
    if (els.roomJoinBtn) els.roomJoinBtn.addEventListener('click', handleJoinRoom);
    if (els.roomCodeInput) {
        els.roomCodeInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') handleJoinRoom();
        });
    }
    if (els.roomCopyLinkBtn) els.roomCopyLinkBtn.addEventListener('click', copyInviteLink);
    if (els.roomBannerExit) els.roomBannerExit.addEventListener('click', leaveRoom);

    document.addEventListener('musiic:room-joined', updateRoomUI);
    document.addEventListener('musiic:room-left', updateRoomUI);
    document.addEventListener('musiic:room-state', updateRoomUI);
    document.addEventListener('musiic:room-participants', updateRoomUI);

    updateRoomUI();
}

function toggleRoomModal() {
    if (!els.roomModal) return;
    if (els.roomModal.classList.contains('hidden')) {
        openRoomModal();
    } else {
        closeRoomModal();
    }
}

export function openRoomModal(prefillRoomId = '') {
    if (!els.roomModal) return;
    renderRoomModalContent(prefillRoomId);
    els.roomModal.classList.remove('hidden');
}

export function closeRoomModal() {
    if (!els.roomModal) return;
    els.roomModal.classList.add('hidden');
}

function renderRoomModalContent(prefillRoomId = '') {
    if (!els.roomModalTitle || !els.roomModalBody) return;

    if (isInRoom()) {
        const roomId = getRoomId();
        const count = state.room.participantCount || 1;
        els.roomModalTitle.textContent = '一起听';
        els.roomModalBody.innerHTML = `
            <div class="space-y-4">
                <div class="flex items-center justify-between p-3 rounded-xl bg-base-200/50">
                    <div>
                        <p class="text-xs text-base-content/60">房间号</p>
                        <p class="text-lg font-bold tracking-widest font-mono">${roomId}</p>
                    </div>
                    <button id="roomCopyLinkBtn" class="btn btn-sm btn-primary">复制链接</button>
                </div>
                <p class="text-sm text-base-content/70">当前 ${count} 人在线</p>
                <button id="roomLeaveBtn" class="btn btn-error btn-block">退出房间</button>
            </div>
        `;
        document.getElementById('roomCopyLinkBtn').addEventListener('click', copyInviteLink);
        document.getElementById('roomLeaveBtn').addEventListener('click', () => { leaveRoom(); closeRoomModal(); });
        return;
    }

    els.roomModalTitle.textContent = '一起听';
    els.roomModalBody.innerHTML = `
        <div class="space-y-4">
            <button id="roomCreateBtn" class="btn btn-primary btn-block">创建房间</button>
            <div class="divider text-xs text-base-content/50">或加入已有房间</div>
            <div class="join w-full">
                <input id="roomCodeInput" type="text" placeholder="输入房间号" value="${prefillRoomId}" maxlength="10" class="input input-bordered join-item w-full uppercase">
                <button id="roomJoinBtn" class="btn btn-primary join-item">加入</button>
            </div>
        </div>
    `;
    document.getElementById('roomCreateBtn').addEventListener('click', handleCreateRoom);
    document.getElementById('roomJoinBtn').addEventListener('click', handleJoinRoom);
    const input = document.getElementById('roomCodeInput');
    input.addEventListener('keydown', e => { if (e.key === 'Enter') handleJoinRoom(); });
    input.focus();
}

async function handleCreateRoom() {
    try {
        await createRoom();
        closeRoomModal();
    } catch {
        // createRoom 已提示
    }
}

async function handleJoinRoom() {
    const input = document.getElementById('roomCodeInput');
    const roomId = (input ? input.value : '').trim().toUpperCase();
    if (!roomId) { showToast('请输入房间号', 'warning'); return; }

    const exists = await checkRoomExists(roomId);
    if (!exists) { showToast('房间不存在', 'error'); return; }

    await connectRoom(roomId);
    closeRoomModal();
}

function copyInviteLink() {
    const roomId = getRoomId();
    if (!roomId) return;
    const url = new URL(window.location.href);
    url.searchParams.set('room', roomId);
    navigator.clipboard.writeText(url.toString()).then(
        () => showToast('邀请链接已复制', 'success'),
        () => showToast('复制失败', 'error')
    );
}

function updateRoomUI() {
    renderRoomButton();
    renderRoomBanner();
}

function renderRoomButton() {
    if (!els.roomBtn) return;
    const active = isInRoom();
    els.roomBtn.innerHTML = icon('users', { className: active ? 'text-primary' : '' });
    els.roomBtn.className = active
        ? 'btn btn-circle btn-ghost btn-sm text-primary'
        : 'btn btn-circle btn-ghost btn-sm text-base-content/60';
    els.roomBtn.title = active ? '一起听中' : '一起听';
}

function renderRoomBanner() {
    if (!els.roomBanner) return;
    const active = isInRoom();
    els.roomBanner.classList.toggle('hidden', !active);
    if (!active) return;

    const roomId = getRoomId();
    const count = state.room.participantCount || 1;
    if (els.roomBannerCode) els.roomBannerCode.textContent = roomId;
    if (els.roomBannerCount) els.roomBannerCount.textContent = `${count} 人在线`;
}
