"""自动清理过期动态/笔记。"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from .client import NCMClient

log = logging.getLogger("ncm.cleanup")


def cleanup_events(client: NCMClient, max_age_hours: int = 24) -> int:
    """删除自己发布的、超过 max_age_hours 小时的动态。"""
    deleted = 0
    try:
        r = client.weapi_post("/weapi/event/get", {"pagesize": 30, "page": 1})
        events = r.get("events") or []
        now = time.time() * 1000
        for e in events:
            eid = e.get("id")
            publish_time = e.get("publishTime", 0)
            if now - publish_time > max_age_hours * 3600 * 1000:
                try:
                    client.eapi_post("https://interface3.music.163.com/eapi/event/delete", {"id": eid})
                    log.info("删除过期动态: %s", eid)
                    deleted += 1
                    time.sleep(2)
                except Exception as ex:
                    log.warning("删除动态 %s 失败: %s", eid, ex)
    except Exception as e:
        log.warning("清理动态失败: %s", e)
    return deleted
