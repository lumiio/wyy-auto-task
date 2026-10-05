"""歌曲点赞后自动取消。"""
from __future__ import annotations

import logging
import random
import time

from .client import NCMClient

log = logging.getLogger("ncm.song_like")


def like_and_unlike_song(client: NCMClient, track_id: int) -> bool:
    """歌曲点赞后自动取消。"""
    # 点赞
    try:
        r = client.weapi_post("/weapi/song/like", {
            "trackId": track_id,
            "like": True,
        })
        if r.get("code") != 200:
            log.warning("点赞歌曲失败: %s", r)
            return False
        log.info("已点赞歌曲 %s", track_id)
    except Exception as e:
        log.warning("点赞歌曲失败: %s", e)
        return False

    # 等 3-5 秒再取消
    time.sleep(random.uniform(3, 5))

    # 取消点赞
    try:
        r = client.weapi_post("/weapi/song/like", {
            "trackId": track_id,
            "like": False,
        })
        if r.get("code") != 200:
            log.warning("取消点赞歌曲失败: %s", r)
            return False
        log.info("已取消点赞歌曲 %s", track_id)
        return True
    except Exception as e:
        log.warning("取消点赞歌曲失败: %s", e)
        return False
