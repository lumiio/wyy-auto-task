"""刷指定歌曲播放量。"""
from __future__ import annotations

import json
import logging
import random
import time

from .client import NCMClient

log = logging.getLogger("ncm.song_play")


def play_song(client: NCMClient, song_id: int, play_time: int = 200) -> bool:
    """刷指定歌曲播放量。"""
    logs = [
        {
            "action": "play",
            "json": {
                "type": "song",
                "wifi": random.choice([0, 0, 0, 1]),
                "download": 0,
                "id": song_id,
                "time": play_time,
                "end": "playend",
                "source": "list",
                "sourceId": "",
                "mainsite": "1",
                "content": "",
            },
        }
    ]
    body = {"logs": json.dumps(logs, separators=(",", ":"))}
    try:
        r = client.weapi_post("/weapi/feedback/weblog", body)
        log.info("刷歌 %s 成功", song_id)
        return True
    except Exception as e:
        log.warning("刷歌 %s 失败: %s", song_id, e)
        return False


def play_songs(client: NCMClient, song_ids: list[int], times: int = 1) -> None:
    """刷多首歌曲播放量。"""
    for _ in range(times):
        for sid in song_ids:
            play_song(client, sid)
            time.sleep(random.uniform(3, 8))
