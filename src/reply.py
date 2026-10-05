"""私信自动回复。"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.reply")

_DEFAULT_REPLIES = [
    "你好~我现在不方便看手机，稍后回复你。",
    "收到啦，晚点回你~",
    "你好呀，有事留言吧。",
]


def get_recent_contacts(client: NCMClient, limit: int = 20) -> list[dict]:
    """获取最近联系人列表。"""
    try:
        r = client.weapi_post("/weapi/msg/private/users", {
            "limit": limit,
            "offset": 0,
            "total": "true",
        })
        return r.get("msgs", [])
    except Exception as e:
        log.warning("获取最近联系人失败: %s", e)
        return []


def send_text(client: NCMClient, user_ids: list[int], msg: str) -> bool:
    """发送文本私信。"""
    try:
        r = client.weapi_post("/weapi/msg/private/send", {
            "type": "text",
            "msg": msg,
            "userIds": json.dumps(user_ids),
        })
        return r.get("code") == 200
    except Exception as e:
        log.warning("发送私信失败: %s", e)
        return False


class PrivateMsgResponder:
    """私信自动回复器。"""

    def __init__(
        self,
        client: NCMClient,
        state_path: Path,
        default_text: str | None = None,
        rules: list[dict] | None = None,
    ):
        self.client = client
        self.state_path = state_path
        self.default_text = default_text or random.choice(_DEFAULT_REPLIES)
        self.rules = rules or []
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text())
            except Exception:
                pass
        return {"replied": {}}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False))

    def poll_once(self) -> None:
        """轮询一次新私信并回复。"""
        try:
            contacts = get_recent_contacts(self.client, limit=10)
        except RiskControlError:
            return

        for contact in contacts:
            user = contact.get("user", {})
            user_id = user.get("userId") or user.get("id")
            if not user_id:
                continue

            new_count = contact.get("newMsgCount", 0)
            if new_count <= 0:
                continue

            # 检查是否已经回复过这个用户的最新消息
            last_msg_time = contact.get("lastMsgTime", 0)
            replied_key = str(user_id)
            if self._state["replied"].get(replied_key, 0) >= last_msg_time:
                continue

            # 回复
            reply_text = self._match_rule(contact.get("lastMsg", "")) or self.default_text
            if send_text(self.client, [user_id], reply_text):
                log.info("已回复用户 %s: %s", user.get("nickname"), reply_text)
                self._state["replied"][replied_key] = last_msg_time
                self._save_state()
                time.sleep(random.uniform(2, 5))

    def _match_rule(self, last_msg: str) -> str | None:
        """匹配关键词规则。"""
        try:
            msg_data = json.loads(last_msg)
            msg_text = msg_data.get("msg", "")
        except Exception:
            msg_text = last_msg

        for rule in self.rules:
            if rule.get("keyword", "") in msg_text:
                return rule.get("text")
        return None
