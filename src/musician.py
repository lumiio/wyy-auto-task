"""音乐人任务 + 中间播放抽奖。"""
from __future__ import annotations

import logging
import random
import time

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.musician")


def do_middle_play_lottery(client: NCMClient) -> bool:
    """中间播放抽奖。"""
    try:
        r = client.weapi_post("/weapi/middle/play/do/lottery", {
            "activityId": "6501202",
            "drawCount": "1",
        })
        if r.get("code") == 200:
            log.info("中间播放抽奖成功: %s", r.get("data", {}).get("prizeName", ""))
            return True
        log.info("抽奖失败: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("中间播放抽奖失败: %s", e)
        return False


def musician_sign(client: NCMClient) -> bool:
    """音乐人签到。"""
    try:
        r = client.weapi_post("/weapi/creator/user/access", {})
        if r.get("code") == 200:
            log.info("音乐人签到成功")
            return True
        log.info("音乐人签到失败: %s", r.get("message", ""))
        return False
    except Exception as e:
        log.warning("音乐人签到失败: %s", e)
        return False


def get_musician_tasks(client: NCMClient) -> list[dict]:
    """获取音乐人任务列表。"""
    try:
        r = client.weapi_post("/weapi/nmusician/workbench/mission/cycle/list", {})
        return r.get("data", {}).get("list", [])
    except Exception as e:
        log.warning("获取音乐人任务失败: %s", e)
        return []


def claim_musician_reward(client: NCMClient, task_id: str) -> bool:
    """领取音乐人任务奖励。"""
    try:
        r = client.weapi_post("/weapi/nmusician/workbench/mission/reward/obtain", {
            "missionId": task_id,
        })
        return r.get("code") == 200
    except Exception as e:
        log.warning("领取音乐人任务奖励失败: %s", e)
        return False


def run_musician_tasks(client: NCMClient) -> bool:
    """执行音乐人任务。"""
    # 音乐人签到
    musician_sign(client)
    time.sleep(random.uniform(2, 4))

    # 获取任务列表
    tasks = get_musician_tasks(client)
    if not tasks:
        log.info("没有音乐人任务")
        return True

    for task in tasks:
        task_id = task.get("id")
        status = task.get("status")
        name = task.get("name", "")

        if status == 3:  # 可领取
            if claim_musician_reward(client, task_id):
                log.info("领取音乐人任务奖励: %s", name)
            time.sleep(random.uniform(2, 4))

    return True
