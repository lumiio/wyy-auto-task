"""云贝广告任务：听歌/看视频得云贝，单日上限 10 次 × 150 = 1500 云贝/天。"""
from __future__ import annotations

import logging
import time

from .client import NCMClient

log = logging.getLogger("ncm.yunbei_ad")


def claim_all(client: NCMClient, max_times: int = 10) -> int:
    """自动领取所有云贝广告任务奖励。"""
    claimed = 0
    for i in range(max_times):
        try:
            r = client.weapi_post(
                "/weapi/ad/power/yunbei/distribution/create",
                {"yunbeiAmount": 150},
            )
            if r.get("code") == 200 and r.get("data") is True:
                claimed += 150
                log.info("领取云贝广告任务成功，+150 云贝（第 %d/%d 次）", i + 1, max_times)
                time.sleep(0.8)
            else:
                log.info("云贝广告任务已达上限: %s", r.get("message"))
                break
        except Exception as e:
            log.warning("领取云贝广告任务失败: %s", e)
            break
    return claimed
