"""每日刷歌 + 累计听歌时长。

网易云规则：
- 单首必须 >60 秒才计入听歌量
- 每天最多算 300 首，且必须是当日没听过的新歌
- 听歌时长是所有有效播放的累计，不设硬上限

本模块同时追踪两个目标：
  1. 听歌数量（默认 300）
  2. 听歌时长（默认 120 分钟）
"""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .antiban import (
    CircuitBreaker,
    RiskControlError,
    is_countable,
    jitter_daily_target,
    pick_end_type,
    pick_play_duration,
)
from .client import NCMClient

log = logging.getLogger("ncm.scrobble")


@dataclass
class Song:
    sid: int
    full_duration_sec: int
    source: str
    source_id: int


class Scrobbler:
    def __init__(
        self,
        client: NCMClient,
        state_path: Path,
        daily_target: int = 300,
        daily_listen_minutes: int = 720,
        breaker: CircuitBreaker | None = None,
    ):
        self.client = client
        self.state_path = state_path
        self.daily_target = daily_target
        self.daily_listen_sec = daily_listen_minutes * 60
        self.breaker = breaker or CircuitBreaker()
        self._state = self._load_state()

    def _load_state(self) -> dict:
        today = date.today().isoformat()
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text("utf-8"))
                if data.get("date") == today:
                    # 兼容旧格式
                    data.setdefault("seconds", 0)
                    data.setdefault("valid_count", 0)
                    return data
            except Exception as e:
                log.warning("状态文件损坏，重建: %s", e)
        return {"date": today, "ids": [], "seconds": 0, "valid_count": 0}

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, ensure_ascii=False), "utf-8")

    @property
    def done_today(self) -> int:
        return self._state.get("valid_count", len(self._state["ids"]))

    @property
    def seconds_today(self) -> int:
        return self._state.get("seconds", 0)

    def status_line(self) -> str:
        return (
            f"今日已刷有效歌曲 {self.done_today} 首，"
            f"累计听歌 {self.seconds_today // 60} 分 {self.seconds_today % 60} 秒"
        )

    def _fetch_songs(self, needed: int) -> list[Song]:
        toplist_resp = self.client.plain_get("/api/toplist")
        toplists = toplist_resp.get("list", [])
        if not toplists:
            raise RuntimeError("未拿到任何排行榜")

        picked: list[Song] = []
        already = set(self._state["ids"])
        for top in toplists:
            if len(picked) >= needed:
                break
            top_id = top["id"]
            detail = self.client.plain_get("/api/v6/playlist/detail", {"id": str(top_id)})
            playlist = detail.get("playlist") or {}
            tracks = playlist.get("tracks") or []
            for t in tracks:
                sid = t["id"]
                if sid in already:
                    continue
                picked.append(
                    Song(
                        sid=sid,
                        full_duration_sec=max(30, t.get("dt", 200000) // 1000),
                        source="toplist",
                        source_id=top_id,
                    )
                )
                already.add(sid)
                if len(picked) >= needed:
                    break
            time.sleep(random.uniform(0.8, 1.5))
        return picked

    def _report_one(self, song: Song) -> int:
        """上报一首，返回本次实际上报的播放秒数。"""
        play_sec = pick_play_duration(song.full_duration_sec)
        end_type = pick_end_type(play_sec, song.full_duration_sec)
        logs = [
            {
                "action": "play",
                "json": {
                    "type": "song",
                    "wifi": random.choice([0, 0, 0, 1]),
                    "download": 0,
                    "id": song.sid,
                    "time": play_sec,
                    "end": end_type,
                    "source": song.source,
                    "sourceId": song.source_id,
                    "mainsite": "1",
                    "content": f"id={song.source_id}",
                },
            }
        ]
        body = {"logs": json.dumps(logs, separators=(",", ":"))}
        self.client.weapi_post("/weapi/feedback/weblog", body)
        return play_sec

    def run(self) -> int:
        if self.breaker.is_open:
            log.warning("熔断器打开，跳过本轮刷歌")
            return self.done_today

        target = jitter_daily_target(self.daily_target)
        remain_count = target - self.done_today
        remain_sec = self.daily_listen_sec - self.seconds_today
        log.info("开始刷歌：%s", self.status_line())

        if remain_count <= 0 and remain_sec <= 0:
            log.info("数量和时长均已达标，跳过")
            return self.done_today

        # 需要补的首数：至少补齐数量差；时长不够时再额外补
        need_songs = max(remain_count, 0)
        if remain_sec > 0:
            # 平均每首 ~220 秒，估算要补多少首
            need_songs = max(need_songs, int(remain_sec / 220) + 5)

        log.info("本轮计划上报 %d 首", need_songs)
        songs = self._fetch_songs(need_songs)

        ok = 0
        try:
            for i, song in enumerate(songs, 1):
                if self.breaker.is_open:
                    log.warning("刷歌途中熔断，本轮提前结束")
                    break
                # 两个目标都达成就停
                if (self.done_today >= target
                        and self.seconds_today >= self.daily_listen_sec):
                    log.info("数量和时长均达标，提前结束")
                    break
                try:
                    play_sec = self._report_one(song)
                    self._state["ids"].append(song.sid)
                    self._state["seconds"] = self.seconds_today + play_sec
                    if is_countable(play_sec):
                        self._state["valid_count"] = self.done_today + 1
                    ok += 1
                    if ok % 10 == 0:
                        self._save_state()
                        log.info("进度: %s", self.status_line())
                except RiskControlError:
                    log.warning("刷歌命中风控，立即停止")
                    break
                except Exception as e:
                    log.warning("第 %d 首 %s 上报异常: %s", i, song.sid, e)
                time.sleep(random.uniform(3, 8))
        finally:
            self._save_state()
        log.info("本轮结束：%s", self.status_line())
        return self.done_today
