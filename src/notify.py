"""推送通知：Server 酱（sct.ftqq.com）。

在 sct.ftqq.com 用微信扫码登录，拿到 SENDKEY 填到 config.yaml 即可。
免费版每天 5 条，日常汇总 + 偶发告警够用。
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("ncm.notify")

SERVERCHAN_URL = "https://sctapi.ftqq.com/{key}.send"


class Notifier:
    def __init__(self, sendkey: str | None = None):
        self.sendkey = (sendkey or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.sendkey)

    def send(self, title: str, desp: str = "") -> bool:
        if not self.enabled:
            return False
        try:
            r = requests.post(
                SERVERCHAN_URL.format(key=self.sendkey),
                data={"title": title[:32], "desp": desp},
                timeout=10,
            )
            data = r.json()
            if data.get("code") == 0:
                log.info("推送成功: %s", title)
                return True
            log.warning("推送失败: %s", data)
        except Exception as e:
            log.warning("推送异常: %s", e)
        return False
