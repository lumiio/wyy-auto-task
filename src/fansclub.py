"""乐迷团每日任务：通过 interface3 eapi 接口完成播放/分享/点赞任务。

接口来源：chaunsin/netease-cloud-music v0.8.1 api/eapi/fansgroup.go
- 任务列表:  POST https://interface3.music.163.com/eapi/fans/group/mission/all?fansGroupId=xxx
- 进度上报:  POST https://interface3.music.163.com/eapi/fans/group/mission/forward/progress?resourceId=xxx&action=play|share&fansGroupId=null&resourceType=4
- 笔记列表:  POST https://interface3.music.163.com/eapi/fans/group/feed/recommend/get?artistSelf=0&cursor=0&fansGroupId=xxx&size=10
- 点赞笔记:  POST https://interface3.music.163.com/eapi/resource/like  body={threadId, appLogExt}

注意：host 必须是 interface3.music.163.com，不是 music.163.com。
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.fansclub")

IFACE = "https://interface3.music.163.com"


def _parse_button_url(task: dict) -> dict:
    """从任务 button.url 里解析出 actionMnbName / songIds 等参数。"""
    raw = (task.get("button") or {}).get("url") or ""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _mission_song_ids(task: dict) -> list[int]:
    """从任务 button.url 里取出需要播放/分享的歌曲 ID 列表。"""
    info = _parse_button_url(task)
    params = info.get("actionMnbParams") or {}
    return params.get("songIds") or []


def _eapi(c: NCMClient, path: str, body: dict) -> dict:
    """eapi_post 完整 URL 包装。"""
    return c.eapi_post(IFACE + path, body)


def run_fansclub_tasks(c: NCMClient, group_id: str) -> dict[str, Any]:
    """执行乐迷团每日任务。返回执行摘要。"""
    summary: dict[str, Any] = {"group_id": group_id, "done": [], "skipped": [], "failed": []}

    # 1. 拉任务列表
    try:
        r = _eapi(c, f"/eapi/fans/group/mission/all?fansGroupId={group_id}",
                  {"fansGroupId": group_id})
    except RiskControlError:
        summary["failed"].append("任务列表拉取被风控")
        return summary

    if r.get("code") != 200:
        summary["failed"].append(f"任务列表返回 code={r.get('code')}")
        return summary

    tasks = (r.get("data", {}).get("normal") or {}).get("data") or []
    log.info("乐迷团：拉到 %d 个任务", len(tasks))

    for task in tasks:
        title = task.get("title", "")
        status = task.get("status")
        cur = task.get("currentProgress", 0)
        total = task.get("allProgress", 0)

        if status == "COMPLETED":
            summary["skipped"].append(f"{title}({cur}/{total}) 已完成")
            continue

        try:
            if title == "播放歌曲":
                _do_play(c, group_id, task)
            elif title == "分享歌曲":
                _do_share(c, group_id, task)
            elif title == "点赞乐迷笔记":
                _do_like_notes(c, group_id, need=total - cur)
            elif "评论" in title:
                try:
                    _do_comment_song(c, group_id, task)
                    summary["done"].append("评论歌曲(已评论并删除)")
                except RiskControlError:
                    summary["skipped"].append("评论歌曲(风控)")
            elif title == "发布图文笔记":
                try:
                    # 发笔记前预热：模拟正常用户先逛一圈
                    _warmup(c, group_id)
                    event_id = _do_publish_note(c, group_id)
                    if event_id:
                        time.sleep(random.uniform(8, 15))
                        _do_delete_note(c, event_id)
                        summary["done"].append("发布图文笔记(已发并删除)")
                    else:
                        summary["skipped"].append("发布图文笔记(风控,等明天养号)")
                except RiskControlError:
                    summary["skipped"].append("发布图文笔记(风控熔断,明天再试)")
                except Exception as e:
                    log.warning("发笔记异常: %s", e)
                    summary["skipped"].append(f"发布图文笔记(异常: {e})")
            else:
                summary["skipped"].append(f"{title}(未识别)")
        except RiskControlError:
            summary["failed"].append(f"{title} 触发风控")
            break
        except Exception as e:
            log.warning("乐迷团任务 %s 异常: %s", title, e)
            summary["failed"].append(f"{title}: {e}")

    # 2. 复核一次任务状态
    try:
        r2 = _eapi(c, f"/eapi/fans/group/mission/all?fansGroupId={group_id}",
                   {"fansGroupId": group_id})
        for t in (r2.get("data", {}).get("normal") or {}).get("data") or []:
            summary["done"].append(
                f"{t['title']}: {t['currentProgress']}/{t['allProgress']} {t['status']}")
    except Exception:
        pass

    return summary


def _do_play(c: NCMClient, group_id: str, task: dict) -> None:
    """播放任务：对任务列表给的每首歌调一次 forward/progress action=play。"""
    song_ids = _mission_song_ids(task)
    need = task.get("allProgress", 2) - task.get("currentProgress", 0)
    picked = song_ids[:need] if song_ids else []
    for sid in picked:
        url = (f"/eapi/fans/group/mission/forward/progress"
               f"?resourceId={sid}&action=play&fansGroupId=null&resourceType=4")
        _eapi(c, url, {"resourceId": str(sid), "action": "play",
                       "fansGroupId": "null", "resourceType": "4"})
        log.info("乐迷团播放上报 songId=%s", sid)
        time.sleep(random.uniform(2, 4))


def _do_share(c: NCMClient, group_id: str, task: dict) -> None:
    """分享任务：对任务列表里的一首歌调 forward/progress action=share。"""
    song_ids = _mission_song_ids(task)
    if not song_ids:
        log.warning("乐迷团分享任务没拿到 songIds")
        return
    sid = random.choice(song_ids)
    url = (f"/eapi/fans/group/mission/forward/progress"
           f"?resourceId={sid}&action=share&fansGroupId=null&resourceType=4")
    _eapi(c, url, {"resourceId": str(sid), "action": "share",
                   "fansGroupId": "null", "resourceType": "4"})
    log.info("乐迷团分享上报 songId=%s", sid)
    time.sleep(random.uniform(2, 4))


def _do_comment_song(c: NCMClient, group_id: str, task: dict) -> None:
    """评论一首歌，完成后自动删除评论。"""
    comments = [
        "这首歌真的太好听了，循环一天",
        "Sophis的歌越听越有味道，旋律绝了",
        "单曲循环中，每一首都好戳我",
    ]
    # 用任务里给的歌
    song_ids = _mission_song_ids(task)
    if not song_ids:
        song_ids = [29041788]  # 默认 I'm Callin'
    sid = song_ids[0]
    content = random.choice(comments)

    # 发评论
    r = c.weapi_post("/weapi/resource/comments/add", {
        "threadId": f"R_SO_4_{sid}",
        "content": content,
        "commentType": 0,
    })
    if r.get("code") != 200:
        log.warning("评论失败 code=%s", r.get("code"))
        return
    cid = (r.get("comment") or {}).get("commentId")
    log.info("已评论 songId=%s commentId=%s", sid, cid)

    # 等 3 秒再删
    time.sleep(random.uniform(3, 5))
    try:
        c.weapi_post("/weapi/resource/comments/delete", {
            "threadId": f"R_SO_4_{sid}",
            "commentId": cid,
        })
        log.info("已删除评论 commentId=%s", cid)
    except Exception as e:
        log.warning("删除评论失败: %s", e)


def _do_like_notes(c: NCMClient, group_id: str, need: int) -> None:
    """点赞乐迷笔记：点 need 个赞，完成后自动取消。"""
    liked_threads = []
    cursor = "0"
    pages = 0
    while len(liked_threads) < need and pages < 5:
        pages += 1
        url = (f"/eapi/fans/group/feed/recommend/get"
               f"?artistSelf=0&cursor={cursor}&fansGroupId={group_id}&size=20")
        r = _eapi(c, url, {"artistSelf": "0", "cursor": cursor,
                           "fansGroupId": group_id, "size": "20"})
        recs = (r.get("data") or {}).get("records") or []
        if not recs:
            break
        for rec in recs:
            if len(liked_threads) >= need:
                break
            info = rec.get("info") or {}
            if info.get("liked"):
                continue
            tid = rec.get("threadId")
            if not tid:
                continue
            try:
                _eapi(c, "/eapi/resource/like",
                      {"threadId": tid, "appLogExt": ""})
                liked_threads.append(tid)
                log.info("乐迷团点赞笔记 by %s",
                         (rec.get("user") or {}).get("nickname", "?"))
                time.sleep(random.uniform(1.5, 3))
            except RiskControlError:
                raise
            except Exception as e:
                log.warning("点赞笔记失败: %s", e)
        cursor = (r.get("data") or {}).get("page", {}).get("cursor") or "0"

    # 等 3~5 秒再取消点赞
    if liked_threads:
        log.info("点赞完成 %d 个，准备取消", len(liked_threads))
        time.sleep(random.uniform(3, 5))
        for tid in liked_threads:
            try:
                _eapi(c, "/eapi/resource/like",
                      {"threadId": tid, "appLogExt": "", "like": "false"})
                log.info("已取消点赞 %s", tid)
                time.sleep(random.uniform(1, 2))
            except Exception as e:
                log.warning("取消点赞失败: %s", e)


# ---------- 发布/删除乐迷团图文笔记 ----------

_NOTE_TEXTS = [
    "今天也在循环Sophis的歌，真的越听越上头，每一首都好有感觉，旋律绝了",
    "Sophis的歌真的是宝藏，单曲循环一整天都不腻，旋律太舒服了",
    "最近无限循环Sophis，每首歌都戳中耳朵，越听越有味道，推荐大家都去听",
]


def _do_publish_note(c: NCMClient, group_id: str) -> int | None:
    """上传配图 + 发乐迷团笔记。成功返回 event_id，失败返回 None。"""
    import hashlib
    import uuid as uuidlib
    from pathlib import Path

    img_path = Path(__file__).parent.parent / "assets" / "miss.jpg"
    if not img_path.exists():
        log.warning("笔记配图不存在: %s", img_path)
        return None

    data = img_path.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    ext = "jpg"

    # 1. 拿上传节点
    node = c.session.get(
        "http://wanproxy.127.net/lbs?version=1.0&bucketname=cloudmusic",
        timeout=10).json()["upload"][0]

    # 2. 拿 NOS token
    tok = c.eapi_post(
        "https://music.163.com/eapi/nos/token/alloc",
        {"filename": "miss.jpg", "local": "false", "nos_product": 0,
         "fileSize": len(data), "md5": md5, "ext": ext, "type": "image"})
    res = tok.get("result") or {}
    if not res:
        log.warning("nos token 失败: %s", tok)
        return None

    # 3. PUT 上传
    up_url = f"{node}/{res['bucket']}/{res['objectKey']}?version=1.0&offset=0&complete=true"
    r = c.session.put(up_url, data=data,
                      headers={"X-Nos-Token": res["token"],
                               "Content-Type": "image/jpeg"}, timeout=30)
    if r.status_code != 200:
        log.warning("PUT 上传失败: %s", r.status_code)
        return None

    # 4. 拿图片信息
    img = c.eapi_post("https://music.163.com/eapi/upload/event/img/v1",
                      {"imgid": res["docId"], "format": ext})
    pi = (img.get("picInfo") or {})
    if not pi:
        log.warning("img info 失败: %s", img)
        return None

    # 5. 拿乐迷团 boardId
    detail = c.eapi_post(
        f"{IFACE}/eapi/social/fansgroup/bff/detail/get?groupId={group_id}&scene=",
        {"groupId": group_id, "scene": ""})
    fi = (detail.get("data") or {}).get("fansGroupInfo") or {}
    board_id = fi.get("boardId")
    group_name = fi.get("fansGroupName") or "乐迷团"
    if not board_id:
        log.warning("拿不到 boardId")
        return None

    pic = {"originId": str(pi.get("originId", "")),
           "squareId": str(pi.get("squareId", "")),
           "rectangleId": str(pi.get("rectangleId", "")),
           "pcSquareId": str(pi.get("pcSquareId", "")),
           "pcRectangleId": str(pi.get("pcRectangleId", "")),
           "originJpgId": str(pi.get("originJpgId") or 0),
           "width": 1440, "height": 1440, "index": 0}
    ail = json.dumps([{"id": str(board_id), "type": 3, "subType": 11,
                       "name": group_name, "selected": True, "canChange": True}],
                     separators=(",", ":"))

    body = {
        "msg": random.choice(_NOTE_TEXTS),
        "type": "noresource",
        "uuid": uuidlib.uuid4().hex,
        "pics": json.dumps([pic], separators=(",", ":")),
        "addComment": False,
        "privacySetting": "0",
        "socialSpaceVisible": 1,
        "activityInfoList": ail,
    }
    r = c.eapi_post(f"{IFACE}/eapi/note/share/friends/resource", body)
    if r.get("code") != 200:
        log.warning("发笔记被风控 code=%s msg=%s", r.get("code"), r.get("message"))
        return None
    eid = r.get("id")
    log.info("乐迷团笔记已发布 event_id=%s", eid)
    return eid


def _do_delete_note(c: NCMClient, event_id: int) -> None:
    """删除动态。"""
    try:
        c.eapi_post(f"{IFACE}/eapi/event/delete", {"id": event_id})
        log.info("乐迷团笔记已删除 event_id=%s", event_id)
    except Exception as e:
        log.warning("删除笔记失败: %s", e)


def _warmup(c: NCMClient, group_id: str) -> None:
    """发笔记前预热：模拟正常用户浏览一圈，降低风控概率。"""
    log.info("发笔记前预热中...")
    # 1. 拉一次任务列表（模拟进乐迷团首页）
    try:
        _eapi(c, f"/eapi/fans/group/mission/all?fansGroupId={group_id}",
              {"fansGroupId": group_id})
        time.sleep(random.uniform(2, 4))
    except Exception:
        pass
    # 2. 刷一下乐迷团 feed（模拟看笔记流）
    try:
        _eapi(c, f"/eapi/fans/group/feed/recommend/get?artistSelf=0&cursor=0&fansGroupId={group_id}&size=5",
              {"artistSelf": "0", "cursor": "0", "fansGroupId": group_id, "size": "5"})
        time.sleep(random.uniform(3, 5))
    except Exception:
        pass
    # 3. 访问一下歌手主页（weblog 上报浏览）
    try:
        c.weapi_post("/weapi/artist/intro", {"id": 1050241})
        time.sleep(random.uniform(2, 4))
    except Exception:
        pass
    log.info("预热完成，开始发笔记")
