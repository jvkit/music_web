"""用户反馈与日志上报（设置页「关于与反馈」用，登录后可调）。"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, Field

from yinhe.config import get_config_dir
from yinhe.web.users_api import _resolve_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class LogUploadRequest(BaseModel):
    lines: list[str] = Field(default_factory=list)


def _feedback_path() -> Path:
    return get_config_dir() / "feedback.jsonl"


def _logs_dir() -> Path:
    d = get_config_dir() / "logs_upload"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/feedback")
def api_feedback(req: FeedbackRequest, authorization: Optional[str] = Header(default=None)):
    """用户反馈：追加写入 feedback.jsonl，作者排查用。"""
    username = _resolve_user(authorization)
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "user": username,
        "text": req.text.strip(),
    }
    path = _feedback_path()
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True}


@router.post("/logs")
def api_upload_logs(req: LogUploadRequest, authorization: Optional[str] = Header(default=None)):
    """客户端运行日志上报：整段写入 logs_upload/<user>_<ts>.log，供调试排查。"""
    username = _resolve_user(authorization)
    if not req.lines:
        raise HTTPException(status_code=400, detail="日志为空")
    if len(req.lines) > 2000:
        raise HTTPException(status_code=400, detail="日志过长")
    fname = f"{username}_{int(time.time())}.log"
    (_logs_dir() / fname).write_text("\n".join(req.lines), encoding="utf-8")
    logger.info("日志上报：%s（%d 行）", username, len(req.lines))
    return {"ok": True, "file": fname}
