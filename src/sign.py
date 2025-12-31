"""每日签到：云贝/乐签。"""
from __future__ import annotations

import logging

from .client import NCMClient

log = logging.getLogger("ncm.sign")


def daily_sign(client: NCMClient) -> bool:
    """执行每日签到。返回 True 表示本次成功（或已签过）。

    type=0 安卓端，type=1 web/PC 端。安卓端奖励更稳，优先用 0，失败再退 1。
    """
    for stype in (0, 1):
        resp = client.weapi_post("/weapi/point/dailyTask", {"type": stype})
        code = resp.get("code")
        if code == 200:
            log.info("签到成功（type=%s），获得积分: %s", stype, resp.get("point"))
            return True
        if code == -2:
            log.info("今日已签到过，跳过")
            return True
        log.warning("签到 type=%s 返回 code=%s: %s", stype, code, resp)
    log.error("两种签到类型均失败")
    return False
