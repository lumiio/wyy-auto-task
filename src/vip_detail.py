"""会员任务新版。"""
from __future__ import annotations

import logging

from .client import NCMClient

log = logging.getLogger("ncm.vip_tasks_v2")


def get_vip_tasks_v2(client: NCMClient, user_id: int) -> list[dict]:
    """获取会员任务新版。"""
    try:
        r = client.eapi_post(
            "https://music.163.com/api/middle/vip/mission/user/progress/list",
            {
                "taskType": "app_vip_task_center",
                "userId": user_id,
            },
        )
        return r.get("data", [])
    except Exception as e:
        log.warning("获取会员任务新版失败: %s", e)
        return []
