"""保活：定期探活 cookie，失效时打日志。"""
from __future__ import annotations

import logging

from .client import NCMClient

log = logging.getLogger("ncm.keepalive")


def ping(client: NCMClient) -> bool:
    """探活一次。返回 True 表示登录态正常。"""
    try:
        info = client.account_info()
    except Exception as e:
        log.warning("探活请求异常: %s", e)
        return False
    account = info.get("account")
    if account:
        log.info("保活正常：%s (vipType=%s)", account.get("userName"), info.get("vipType"))
        return True
    log.error("保活失败：账号信息为空，cookie 可能已失效，请重新抓取 MUSIC_U")
    return False
