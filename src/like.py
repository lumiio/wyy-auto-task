"""点赞后自动取消点赞。"""
from __future__ import annotations

import logging
import random
import time

from .client import NCMClient

log = logging.getLogger("ncm.like")


def like_and_unlike(client: NCMClient, thread_id: str, for_song: bool = True) -> bool:
    """点赞后自动取消点赞。"""
    # 点赞
    try:
        r = client.weapi_post("/weapi/resource/like", {
            "threadId": thread_id,
            "forSong": for_song,
        })
        if r.get("code") != 200:
            log.warning("点赞失败: %s", r)
            return False
        log.info("已点赞 %s", thread_id)
    except Exception as e:
        log.warning("点赞失败: %s", e)
        return False

    # 等 3-5 秒再取消
    time.sleep(random.uniform(3, 5))

    # 取消点赞
    try:
        r = client.weapi_post("/weapi/resource/like", {
            "threadId": thread_id,
            "forSong": for_song,
            "like": False,
        })
        if r.get("code") != 200:
            log.warning("取消点赞失败: %s", r)
            return False
        log.info("已取消点赞 %s", thread_id)
        return True
    except Exception as e:
        log.warning("取消点赞失败: %s", e)
        return False
