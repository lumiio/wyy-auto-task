"""音乐合伙人（乐迷任务）自动测评 + 分享歌曲到动态。

流程：
  1. 拉 /weapi/music/partner/daily/task/get 拿当日待测评歌曲
  2. 对每首未完成的，随机打 3~5 分 + 选对应标签，提交测评
  3. 额外推荐歌曲同样处理
  4. 分享一首随机歌曲到动态（完成会员任务里的分享指标）
"""
from __future__ import annotations

import logging
import random
import time

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.partner")

# 按分数段选标签（只挑正面的，避免误判差评）
TAGS_BY_SCORE = {
    3: ["3-A-1", "3-B-1", "3-C-1", "3-D-1", "3-E-1"],
    4: ["3-A-2", "3-B-1", "3-C-1", "3-D-2", "3-E-2"],
    5: ["3-A-2", "3-B-1", "3-C-1", "3-D-2", "3-E-2"],
}


def _evaluate_one(client: NCMClient, task_id, work_id, name: str) -> bool:
    score = random.randint(3, 5)
    pool = TAGS_BY_SCORE.get(score, TAGS_BY_SCORE[3])
    tags = ",".join(random.sample(pool, k=min(3, len(pool))))
    body = {
        "taskId": str(task_id),
        "workId": str(work_id),
        "score": str(score),
        "tags": tags,
        "customTags": "[]",
        "comment": "",
        "syncYunCircle": False,
        "syncComment": True,
        "source": "mp-music-partner",
    }
    resp = client.weapi_post("/weapi/music/partner/work/evaluate", body)
    if resp.get("code") == 200:
        log.info("测评完成《%s》 score=%s tags=%s", name, score, tags)
        return True
    log.warning("测评《%s》失败: %s", name, resp)
    return False


def run_partner_tasks(client: NCMClient) -> int:
    """执行一次音乐合伙人测评。返回完成数量。"""
    try:
        resp = client.weapi_post("/weapi/music/partner/daily/task/get", {})
    except RiskControlError:
        return 0

    if resp.get("code") != 200:
        log.warning("拉取音乐合伙人任务失败: %s", resp)
        return 0

    data = resp.get("data") or {}
    works = data.get("works") or []
    recs = data.get("recResources") or []
    log.info("音乐合伙人：基础歌曲 %d 首，额外推荐 %d 首", len(works), len(recs))

    done = 0
    candidates = []
    for w in works:
        if not w.get("completed"):
            work = w.get("work") or {}
            candidates.append((work.get("id"), work.get("resourceId"), work.get("name", "?")))
    for r in recs:
        work = r.get("work") or {}
        # recResources 没有 completed 字段，直接尝试测评（已测的会被服务端拒绝）
        candidates.append((work.get("id"), work.get("resourceId"), work.get("name", "?")))

    for task_id, work_id, name in candidates:
        if not task_id or not work_id:
            continue
        try:
            if _evaluate_one(client, task_id, work_id, name):
                done += 1
        except RiskControlError:
            log.warning("测评命中风控，停止")
            break
        except Exception as e:
            log.warning("测评《%s》异常: %s", name, e)
        time.sleep(random.uniform(3, 6))

    log.info("音乐合伙人完成 %d 首测评", done)
    return done


def share_random_song(client: NCMClient) -> bool:
    """从热门榜随机挑一首歌分享到动态（完成分享类任务）。"""
    try:
        toplist = client.plain_get("/api/toplist")
        tops = toplist.get("list") or []
        if not tops:
            return False
        top = random.choice(tops)
        detail = client.plain_get("/api/v6/playlist/detail", {"id": str(top["id"])})
        tracks = (detail.get("playlist") or {}).get("tracks") or []
        if not tracks:
            return False
        song = random.choice(tracks)
        resp = client.weapi_post(
            "/weapi/share/resource",
            {"type": "song", "id": song["id"]},
        )
        if resp.get("code") == 200:
            log.info("已分享《%s》- %s 到动态", song.get("name"),
                     (song.get("ar") or [{}])[0].get("name", "?"))
            return True
        log.warning("分享歌曲失败: %s", resp)
        return False
    except RiskControlError:
        return False
    except Exception as e:
        log.warning("分享歌曲异常: %s", e)
        return False
