"""云贝中心签到 + 每日任务（关注歌手/红心歌曲/浏览会员中心）。"""
from __future__ import annotations

import logging
import random
import time

from .antiban import RiskControlError
from .client import NCMClient

log = logging.getLogger("ncm.yunbei")

IFACE = "https://interface3.music.163.com"


def yunbei_sign(client: NCMClient) -> bool:
    """云贝中心每日签到。返回 True 表示成功或已签过。"""
    try:
        resp = client.weapi_post("/weapi/pointmall/user/sign", {})
    except RiskControlError:
        return False
    code = resp.get("code")
    if code == 200:
        sign = (resp.get("data") or {}).get("sign")
        if sign:
            log.info("云贝中心签到成功")
        else:
            log.info("云贝中心今日已签过")
        return True
    log.warning("云贝签到返回 code=%s: %s", code, resp)
    return False


def yunbei_todo_list(client: NCMClient) -> list[dict]:
    """拉云贝待完成任务列表。"""
    try:
        r = client.eapi_post(IFACE + "/eapi/usertool/task/todo/query", {})
    except RiskControlError:
        return []
    if r.get("code") != 200:
        return []
    return r.get("data") or []


def yunbei_tasks(client: NCMClient) -> list[str]:
    """跑云贝每日任务：红心一首歌 + 浏览会员中心页面。
    关注歌手任务默认已关注 Sophis，跳过。
    """
    done: list[str] = []
    try:
        tasks = yunbei_todo_list(client)
    except Exception as e:
        log.warning("云贝任务列表失败: %s", e)
        return done

    for t in tasks:
        name = t.get("taskName", "")
        if t.get("completed"):
            continue
        try:
            if name == "红心歌曲":
                # 随机把一首歌加为我喜欢
                r = client.weapi_post("/weapi/v3/song/detail",
                                      {"c": '[{"id":347230}]'})
                sid = (r.get("songs") or [{}])[0].get("id")
                if sid:
                    client.weapi_post("/weapi/radio/like",
                                      {"trackId": sid, "like": "true",
                                       "time": int(time.time() * 1000)})
                    done.append(f"红心歌曲 {sid}")
                    time.sleep(random.uniform(2, 4))
            elif name == "浏览会员中心":
                # 访问一下会员中心页面就算浏览完成
                client.weapi_post("/weapi/vipnewcenter/app/level/task/newlist", {})
                done.append("浏览会员中心")
                time.sleep(random.uniform(2, 4))
            elif name == "关注歌手":
                done.append("关注歌手(已关注Sophis,跳过)")
            elif name == "探索小众歌曲":
                # 用 TrialsongListen 上报听歌
                try:
                    # 先拉每日推荐拿几首歌
                    r = client.eapi_post(
                        "https://interface3.music.163.com/eapi/v3/discovery/recommend/songs", {})
                    songs = r.get("data", {}).get("dailySongs") or []
                    for s in songs[:3]:
                        client.eapi_post(
                            "https://interface3.music.163.com/eapi/vipmall/interest/trialsong/listen",
                            {"songId": str(s["id"]), "albumId": str(s.get("al", {}).get("id", 0)), "scene": 1})
                        time.sleep(random.uniform(2, 4))
                    done.append(f"探索小众歌曲({len(songs[:3])}首)")
                except Exception as e:
                    log.warning("探索小众歌曲失败: %s", e)
            elif name == "访问云音乐商城":
                try:
                    client.weapi_post("/weapi/shop/get", {})
                    done.append("访问云音乐商城")
                    time.sleep(random.uniform(2, 4))
                except Exception as e:
                    log.warning("访问商城失败: %s", e)
        except RiskControlError:
            break
        except Exception as e:
            log.warning("云贝任务 %s 异常: %s", name, e)

    return done

