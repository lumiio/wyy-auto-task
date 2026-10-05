"""会员任务（黑胶 VIP 成长值）自动领取。

策略：先做能自动完成的任务（红心VIP单曲）→ 黑胶乐签 → 一键领奖 → 复查。
"""
from __future__ import annotations

import logging
import random
import time

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.vip")

# VIP 红心任务歌单 ID
_VIP_SONG_PLAYLIST = 8402996200


def _heartbeat_vip_songs(client: NCMClient) -> None:
    """红心 3 首 VIP 单曲（成长值+3）。"""
    try:
        r = client.weapi_post("/weapi/v3/playlist/detail",
                              {"id": _VIP_SONG_PLAYLIST, "n": 1000, "s": 8})
        tracks = r.get("playlist", {}).get("tracks", [])
    except Exception as e:
        log.warning("拉 VIP 歌单失败: %s", e)
        return

    liked = 0
    for t in tracks:
        if liked >= 3:
            break
        try:
            client.weapi_post("/weapi/radio/like",
                              {"trackId": t["id"], "like": "true",
                               "time": int(time.time() * 1000)})
            log.info("VIP任务红心: %s", t["name"])
            liked += 1
            time.sleep(random.uniform(5, 10))
        except RiskControlError:
            log.info("红心触发风控，跳过剩余")
            break
        except Exception as e:
            log.warning("红心失败: %s", e)


def _fetch_task_summary(client: NCMClient) -> tuple[int, int]:
    """返回 (当前已获成长值, 待领成长值)。"""
    resp = client.weapi_post("/weapi/vipnewcenter/app/level/task/newlist", {})
    score = resp.get("taskScore") or resp.get("data", {}).get("taskScore", 0)
    unget = resp.get("unGetAllScore") or resp.get("data", {}).get("unGetAllScore", 0)
    if isinstance(score, dict):  # 兼容嵌套
        score = score.get("score", 0)
    return int(score or 0), int(unget or 0)


def claim_daily_tasks(client: NCMClient) -> bool:
    """执行一次会员任务领取。返回 True 表示正常走完。"""
    # 先做红心 VIP 单曲任务
    _heartbeat_vip_songs(client)

    # 再打黑胶乐签签到
    try:
        client.eapi_post("https://interface.music.163.com/eapi/vip-center-bff/task/sign", {})
        log.info("黑胶乐签已打卡")
    except Exception as e:
        log.warning("黑胶乐签失败: %s", e)

    # 免费领福利：访问福利页面
    try:
        client.eapi_post("https://interface3.music.163.com/eapi/vipnewcenter/app/level/welfare/new/list", {})
        log.info("免费领福利已访问")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        log.warning("免费领福利失败: %s", e)

    # 浏览云贝中心
    try:
        client.eapi_post("https://interface3.music.163.com/eapi/usertool/task/todo/query", {})
        log.info("浏览云贝中心已访问")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        log.warning("浏览云贝中心失败: %s", e)

    # 访问云音乐商城
    try:
        client.weapi_post("/weapi/yunbei/task/visit/mall", {})
        log.info("访问云音乐商城完成")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        log.warning("访问商城失败: %s", e)

    # 浏览VIP中心
    try:
        client.weapi_post("/weapi/vipnewcenter/app/level/task/external", {"type": 1})
        log.info("浏览VIP中心完成")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        log.warning("浏览VIP中心失败: %s", e)

    # 分享任务
    try:
        client.weapi_post("/weapi/point/dailyTask", {"type": 3}, )
        log.info("分享任务完成")
        time.sleep(random.uniform(2, 4))
    except Exception as e:
        log.warning("分享任务失败: %s", e)

    # 每日听3首VIP歌曲：用 TrialsongListen 上报
    try:
        r = client.eapi_post("https://interface3.music.163.com/eapi/v3/discovery/recommend/songs", {})
        songs = r.get("data", {}).get("dailySongs") or []
        for s in songs[:3]:
            client.eapi_post("https://interface3.music.163.com/eapi/vipmall/interest/trialsong/listen",
                             {"songId": str(s["id"]), "albumId": str(s.get("al", {}).get("id", 0)), "scene": 1})
            time.sleep(random.uniform(2, 4))
        log.info("每日听VIP歌曲已完成")
    except Exception as e:
        log.warning("每日听VIP歌曲失败: %s", e)

    try:
        before_score, unget = _fetch_task_summary(client)
    except RiskControlError:
        raise
    except Exception as e:
        log.warning("拉会员任务列表失败: %s", e)
        return False

    log.info("会员任务：当前成长值 %d，待领 %d", before_score, unget)
    if unget <= 0:
        log.info("没有可领的会员任务奖励")
        return True

    # 一键领取
    resp = client.weapi_post("/weapi/vipnewcenter/app/level/task/reward/getall", {})
    if resp.get("code") != 200:
        log.warning("一键领奖返回非 200: %s", resp)
        return False

    # 再拉一次看实际到账
    try:
        after_score, _ = _fetch_task_summary(client)
        delta = after_score - before_score
        log.info("会员任务领奖成功，本次到账 %d 成长值（当前总计 %d）", delta, after_score)
    except Exception as e:
        log.info("一键领奖已提交，但复查失败: %s", e)

    return True
