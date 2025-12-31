"""启动时自动关注指定用户。"""
from __future__ import annotations

import logging

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.follow")


def auto_follow(client: NCMClient, artist_id: int) -> bool:
    """关注指定歌手。已关注则跳过。"""
    try:
        r = client.weapi_post("/weapi/artist/sub", {"artistId": artist_id, "t": 1})
    except Exception:
        return False
    code = r.get("code")
    if code == 200:
        log.info("已关注 artistId=%s", artist_id)
        return True
    log.warning("关注失败 code=%s: %s", code, r.get("message"))
    return False
