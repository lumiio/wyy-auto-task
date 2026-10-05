"""自动获取用户加入的所有乐迷团并完成任务。"""
from __future__ import annotations

import logging
from typing import Any

from .antiban import RiskControlError
from .client import NCMClient
from .fansclub import run_fansclub_tasks

log = logging.getLogger("ncm.fansclub_all")


def get_user_fansgroups(client: NCMClient) -> list[dict[str, Any]]:
    """获取用户加入的所有乐迷团列表。"""
    try:
        r = client.eapi_post(
            "https://music.163.com/api/social/fansgroup/bff/user/groups/get", {}
        )
        return r.get("data", {}).get("groups", [])
    except RiskControlError:
        return []
    except Exception as e:
        log.warning("获取乐迷团列表失败: %s", e)
        return []


def run_all_fansclub_tasks(client: NCMClient) -> list[dict]:
    """自动完成所有乐迷团任务。"""
    groups = get_user_fansgroups(client)
    log.info("获取到 %d 个乐迷团", len(groups))

    results = []
    for g in groups:
        group_id = g["fansGroupId"]
        name = g.get("fansGroupName", group_id)
        log.info("开始处理 %s", name)
        try:
            result = run_fansclub_tasks(client, group_id)
            results.append(result)
        except Exception as e:
            log.warning("乐迷团 %s 任务失败: %s", name, e)
            results.append({"group_id": group_id, "name": name, "error": str(e)})

    return results
