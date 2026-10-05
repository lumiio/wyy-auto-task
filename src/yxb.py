"""云小编任务：签到、领积分、抽奖、领一日会员。"""
from __future__ import annotations

import logging
import random
import time

from .client import NCMClient

log = logging.getLogger("ncm.yxb")


def yxb_sign(client: NCMClient) -> bool:
    """云小编每日签到。"""
    try:
        r = client.weapi_post("/weapi/rep/ugc/user/sign", {})
        if r.get("code") == 200:
            log.info("云小编签到成功")
            return True
        log.info("云小编签到: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("云小编签到失败: %s", e)
        return False


def yxb_user_info(client: NCMClient) -> dict:
    """获取云小编用户详情。"""
    try:
        return client.weapi_post("/weapi/rep/ugc/user/get", {})
    except Exception as e:
        log.warning("获取云小编用户详情失败: %s", e)
        return {}


def yxb_activity_info(client: NCMClient) -> dict:
    """获取云小编活动信息。"""
    try:
        return client.weapi_post("/weapi/rep/ugc/activity/get", {})
    except Exception as e:
        log.warning("获取云小编活动信息失败: %s", e)
        return {}


def yxb_collect_points(client: NCMClient, activity_id: str = "5001") -> bool:
    """领取云小编任务积分。"""
    try:
        r = client.weapi_post("/weapi/rep/ugc/activity/collect", {
            "activityId": activity_id,
        })
        if r.get("code") == 200:
            log.info("云小编领取任务积分成功")
            return True
        log.info("云小编领取任务积分: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("云小编领取任务积分失败: %s", e)
        return False


def yxb_check_vip(client: NCMClient) -> int:
    """查询云小编会员任务状态。
    10: 可领取
    20: 可领取
    30: 已领取
    """
    try:
        r = client.weapi_post("/weapi/rep/ugc/user/vip", {})
        return r.get("data", {}).get("status", 0)
    except Exception as e:
        log.warning("查询云小编会员任务状态失败: %s", e)
        return 0


def yxb_claim_vip(client: NCMClient, activity_id: str = "5001") -> bool:
    """领取云小编一日会员。"""
    try:
        r = client.weapi_post("/weapi/rep/ugc/user/collect-vip", {
            "activityId": activity_id,
        })
        if r.get("code") == 200:
            log.info("云小编领取一日会员成功")
            return True
        log.info("云小编领取一日会员: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("云小编领取一日会员失败: %s", e)
        return False


def yxb_lottery_remain(client: NCMClient, activity_id: str = "6501202") -> int:
    """查询云小编抽奖剩余次数。"""
    try:
        r = client.weapi_post("/weapi/middle/play/lottery/remain/chance", {
            "activityId": activity_id,
        })
        data = r.get("data", {})
        if isinstance(data, dict):
            return data.get("remainChance", 0)
        return int(data) if data else 0
    except Exception as e:
        log.warning("查询云小编抽奖剩余次数失败: %s", e)
        return 0


def yxb_lottery(client: NCMClient, activity_id: str = "6501202") -> bool:
    """云小编每日抽奖。"""
    try:
        r = client.weapi_post("/weapi/middle/play/do/lottery", {
            "activityId": activity_id,
            "drawCount": "1",
        })
        if r.get("code") == 200:
            log.info("云小编抽奖成功: %s", r.get("data", {}).get("prizeName", ""))
            return True
        log.info("云小编抽奖: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("云小编抽奖失败: %s", e)
        return False


def run_yxb_tasks(client: NCMClient) -> bool:
    """执行云小编所有任务。"""
    # 签到
    yxb_sign(client)
    time.sleep(random.uniform(2, 4))

    # 获取活动信息
    activity = yxb_activity_info(client)
    activity_id = activity.get("data", {}).get("activityId", "5001")

    # 领取任务积分
    yxb_collect_points(client, str(activity_id))
    time.sleep(random.uniform(2, 4))

    # 查询会员任务状态
    vip_status = yxb_check_vip(client)
    if vip_status in (10, 20):
        yxb_claim_vip(client, str(activity_id))
        time.sleep(random.uniform(2, 4))

    # 抽奖
    remain = yxb_lottery_remain(client)
    for _ in range(remain):
        yxb_lottery(client)
        time.sleep(random.uniform(3, 5))

    return True
