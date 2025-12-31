"""自动领取云贝。"""
from __future__ import annotations

import logging

from .client import NCMClient

log = logging.getLogger("ncm.yunbei_claim")


def claim_yunbei(client: NCMClient) -> int:
    """领取所有可领取的云贝。"""
    claimed = 0
    try:
        # 先拿任务列表
        r = client.weapi_post("/weapi/usertool/task/todo/query", {})
        tasks = r.get("data", [])
        for t in tasks:
            if t.get("state") == 1:  # 可领取
                user_task_id = t.get("userTaskId")
                deposit_code = t.get("depositCode")
                if user_task_id and deposit_code:
                    resp = client.weapi_post(
                        "/weapi/usertool/task/point/receive",
                        {"userTaskId": user_task_id, "depositCode": deposit_code},
                    )
                    if resp.get("code") == 200:
                        log.info("领取云贝任务: %s", t.get("taskName"))
                        claimed += 1
    except Exception as e:
        log.warning("云贝领取失败: %s", e)
    return claimed
