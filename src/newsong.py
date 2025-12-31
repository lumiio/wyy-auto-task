"""Sophis 新歌监控：每天查一次歌手页，发现新歌自动推送+播放+评论。"""
from __future__ import annotations

import json
import logging
import random
import time
from pathlib import Path

from .antiban import RiskControlError
from .client import NCMClient
from .notify import Notifier

log = logging.getLogger("ncm.newsong")

_COMMENTS = [
    "终于发新歌了！循环起来",
    "新歌第一时间来听，太好听了",
    "Sophis 发新歌必听，旋律绝了",
    "第一时间支持！越听越上头",
]

_STATE_FILE = Path(__file__).parent.parent / "data" / "last_song.json"


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            return json.loads(_STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps(state, ensure_ascii=False))


def check_new_songs(client: NCMClient, notifier: Notifier,
                    artist_id: int = 0) -> list[dict]:
    """检查所有关注歌手的新歌。artist_id 为 0 时自动拉关注列表。"""
    # 拉关注的歌手列表
    try:
        r = client.weapi_post('/weapi/artist/sublist', {'limit': 100, 'offset': 0})
        artists = r.get('data', [])
    except RiskControlError:
        return []

    if artist_id:
        artists = [a for a in artists if a['id'] == artist_id]

    all_new = []
    for artist in artists:
        all_new.extend(_check_one_artist(client, notifier, artist))
    return all_new


def _check_one_artist(client: NCMClient, notifier: Notifier,
                      artist: dict) -> list[dict]:
    """检查单个歌手的新歌。"""
    artist_id = artist['id']
    artist_name = artist['name']
    try:
        r = client.weapi_post("/weapi/artist/songs",
                              {"id": artist_id, "limit": 50, "offset": 0,
                               "order": "time"})
    except RiskControlError:
        return []
    songs = r.get("songs") or []
    if not songs:
        return []

    state = _load_state()
    key = f"artist_{artist_id}"
    known = set(state.get(key, []))
    if not known:
        _save_state({**state, key: [s["id"] for s in songs[:20]]})
        log.info("首次记录 %s 的 %d 首歌", artist_name, len(songs))
        return []

    new_songs = [s for s in songs if s["id"] not in known]
    if not new_songs:
        return []

    log.info("%s 发现 %d 首新歌！", artist_name, len(new_songs))
    for s in new_songs:
        notifier.send(
            f"🎵 {artist_name} 发新歌：{s['name']}",
            f"**{s['name']}**\n\n"
            f"歌手：{artist_name}\n"
            f"专辑：{s.get('al', {}).get('name', '')}\n"
            f"[点击收听](https://music.163.com/song?id={s['id']})")

        try:
            client.weapi_post("/weapi/feedback/weblog", {
                "logs": json.dumps([{
                    "action": "play",
                    "json": {"type": "song", "id": s["id"],
                             "time": s.get("dt", 200000) // 1000,
                             "end": "playend", "source": "artist",
                             "sourceId": artist_id, "mainsite": "1"}
                }], separators=(",", ":"))
            })
            log.info("新歌已播放: %s", s["name"])
            time.sleep(random.uniform(3, 5))
        except Exception as e:
            log.warning("播放新歌失败: %s", e)

        try:
            client.weapi_post("/weapi/resource/comments/add", {
                "threadId": f"R_SO_4_{s['id']}",
                "content": random.choice(_COMMENTS),
                "commentType": 0,
            })
            log.info("新歌已评论: %s", s["name"])
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            log.warning("评论新歌失败: %s", e)

    known.update(s["id"] for s in new_songs)
    _save_state({**state, key: list(known)[-100:]})
    return new_songs
