"""入口：加载配置 → 建客户端 → 注册定时任务 → 阻塞运行。"""
from __future__ import annotations

import logging
import logging.handlers
import random
import sys
from datetime import date
from pathlib import Path

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from .antiban import CircuitBreaker, RiskControlError
from .client import NCMClient
from .keepalive import ping as keepalive_ping
from .notify import Notifier
from .fansclub import run_fansclub_tasks
from .partner import run_partner_tasks, share_random_song
from .reply import PrivateMsgResponder
from .sign import daily_sign
from .vip import claim_daily_tasks
from .yunbei import yunbei_sign, yunbei_tasks
from .follow import auto_follow
from .newsong import check_new_songs
from .musician import do_middle_play_lottery, run_musician_tasks
from .fansclub_all import run_all_fansclub_tasks
from .yxb import run_yxb_tasks
from .yunbei_ad import claim_all as claim_yunbei_ad
from .account_check import check_account
from .yunbei_claim import claim_yunbei
from .vip_detail import get_vip_tasks_v2
from .like import like_and_unlike
from .song_like import like_and_unlike_song

ROOT = Path(__file__).resolve().parent.parent

# 当日任务结果（汇总推送用）
results: dict[str, str] = {}


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(level)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.handlers.TimedRotatingFileHandler(
        log_dir / "bot.log", when="midnight", backupCount=14, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


def load_config(path: Path) -> dict:
    return yaml.safe_load(path.read_text("utf-8"))


def jitter_cron(cron_expr: str, max_minutes: int = 30) -> CronTrigger:
    parts = cron_expr.split()
    minute, hour = int(parts[0]), int(parts[1])
    minute += random.randint(0, max_minutes)
    if minute >= 60:
        hour = (hour + minute // 60) % 24
        minute %= 60
    parts[0], parts[1] = str(minute), str(hour)
    return CronTrigger.from_crontab(" ".join(parts))


def task_wrapper(name: str, fn, notifier: Notifier, *args):
    """包一层任务：成功/失败都记到 results，异常时推送告警。"""
    def _run():
        try:
            ok = fn(*args)
            results[name] = "✓" if ok else "✗"
        except Exception as e:
            results[name] = f"✗ ({e})"
            log.exception("任务 %s 异常", name)
            notifier.send(f"[网易云] {name} 失败", f"{name} 执行出错：{e}")
    return _run


def main() -> None:
    cfg_path = ROOT / "config.yaml"
    if not cfg_path.exists():
        print(f"缺少配置文件 {cfg_path}，请复制 config.example.yaml 为 config.yaml 并填写", file=sys.stderr)
        sys.exit(1)
    cfg = load_config(cfg_path)

    setup_logging(ROOT / "logs", cfg.get("log_level", "INFO"))
    log = logging.getLogger("ncm.main")

    cookie = (cfg.get("cookie") or "").strip()
    if not cookie or "MUSIC_U" not in cookie:
        log.error("config.yaml 里的 cookie 必须包含 MUSIC_U")
        sys.exit(1)

    notifier = Notifier(cfg.get("notify", {}).get("serverchan_sendkey"))
    if notifier.enabled:
        log.info("推送已启用（Server酱）")
    else:
        log.info("未配置 SENDKEY，不开启推送")

    ab = cfg.get("antiban", {})
    breaker = CircuitBreaker(
        fail_threshold=int(ab.get("fail_threshold", 5)),
        cooldown_seconds=int(ab.get("cooldown_seconds", 3600)),
    )

    client = NCMClient(cookie, proxy=cfg.get("proxy") or None, breaker=breaker)

    # 启动时自动关注指定用户
    follow_uid = cfg.get("auto_follow_user_id")
    if follow_uid:
        auto_follow(client, int(follow_uid))

    try:
        if not keepalive_ping(client):
            notifier.send("[网易云] cookie 失效", "启动探活失败，请重新抓 MUSIC_U")
            sys.exit(2)
    except RiskControlError:
        notifier.send("[网易云] 启动即命中风控", "请检查 IP/cookie")
        sys.exit(3)

    data_dir = ROOT / "data"

    reply_cfg = cfg.get("reply", {})
    responder = None
    if reply_cfg.get("enabled", False):
        rules = reply_cfg.get("rules", [])
        responder = PrivateMsgResponder(
            client, state_path=data_dir / "replied.json",
            default_text=reply_cfg.get("default_text", "你好~我现在不在，稍后回复你。"),
            rules=rules,
        )

    sched = BlockingScheduler(timezone=cfg.get("timezone", "Asia/Shanghai"))
    jitter_min = int(cfg.get("schedule", {}).get("cron_jitter_minutes", 30))

    if cfg.get("sign", {}).get("enabled", True):
        cron = cfg.get("schedule", {}).get("sign_cron", "0 8 * * *")
        sched.add_job(task_wrapper("乐签签到", daily_sign, notifier, client),
                      jitter_cron(cron, jitter_min), id="sign", misfire_grace_time=3600)
        # 云贝商城签到紧跟乐签
        sched.add_job(task_wrapper("云贝签到", yunbei_sign, notifier, client),
                      jitter_cron(cron, jitter_min), id="yunbei", misfire_grace_time=3600)
        # 云贝每日任务（红心歌曲/浏览会员中心）
        sched.add_job(task_wrapper("云贝任务", yunbei_tasks, notifier, client),
                      jitter_cron(cron, jitter_min), id="yunbei_tasks", misfire_grace_time=3600)
        log.info("签到任务已注册: cron≈%s", cron)

    if cfg.get("partner", {}).get("enabled", True):
        cron = cfg.get("schedule", {}).get("partner_cron", "30 9 * * *")
        sched.add_job(task_wrapper("乐迷测评", run_partner_tasks, notifier, client),
                      jitter_cron(cron, jitter_min), id="partner", misfire_grace_time=3600)
        sched.add_job(task_wrapper("分享歌曲", share_random_song, notifier, client),
                      jitter_cron(cron, jitter_min), id="share", misfire_grace_time=3600)
        log.info("乐迷+分享已注册: cron≈%s", cron)

    # 乐迷团任务：播放/分享/点赞指定乐迷团的任务
    fc = cfg.get("fansclub", {})
    if fc.get("enabled", False) and fc.get("group_id"):
        fc_cron = cfg.get("schedule", {}).get("fansclub_cron", "35 9 * * *")
        sched.add_job(task_wrapper("乐迷团任务", run_fansclub_tasks, notifier,
                                   client, str(fc["group_id"])),
                      jitter_cron(fc_cron, jitter_min), id="fansclub",
                      misfire_grace_time=3600)
        log.info("乐迷团任务已注册: group_id=%s", fc["group_id"])

    if cfg.get("vip", {}).get("enabled", True):
        cron = cfg.get("schedule", {}).get("vip_cron", "0 10 * * *")
        sched.add_job(task_wrapper("会员领奖", claim_daily_tasks, notifier, client),
                      jitter_cron(cron, jitter_min), id="vip", misfire_grace_time=3600)
        log.info("会员领奖已注册: cron≈%s", cron)

    # 新歌监控（自动拉关注的所有歌手，发新歌自动推送+播放+评论）
    sched.add_job(task_wrapper("新歌监控", check_new_songs, notifier,
                               client, 0),
                  jitter_cron("0 11 * * *", jitter_min), id="newsong",
                  misfire_grace_time=3600)
    log.info("新歌监控已注册（自动监控所有关注歌手）")

    # 所有乐迷团任务
    sched.add_job(task_wrapper("所有乐迷团任务", run_all_fansclub_tasks, notifier, client),
                  jitter_cron("30 11 * * *", jitter_min), id="fansclub_all",
                  misfire_grace_time=3600)
    log.info("所有乐迷团任务已注册")

    # 云小编任务
    sched.add_job(task_wrapper("云小编任务", run_yxb_tasks, notifier, client),
                  jitter_cron("0 12 * * *", jitter_min), id="yxb",
                  misfire_grace_time=3600)
    log.info("云小编任务已注册")

    # 云贝广告任务
    sched.add_job(task_wrapper("云贝广告任务", claim_yunbei_ad, notifier, client),
                  jitter_cron("10 12 * * *", jitter_min), id="yunbei_ad",
                  misfire_grace_time=3600)
    log.info("云贝广告任务已注册")

    # 账号检查
    sched.add_job(task_wrapper("账号检查", check_account, notifier, client),
                  jitter_cron("20 12 * * *", jitter_min), id="account_check",
                  misfire_grace_time=3600)
    log.info("账号检查已注册")

    # 领云贝
    sched.add_job(task_wrapper("领云贝", claim_yunbei, notifier, client),
                  jitter_cron("30 12 * * *", jitter_min), id="yunbei_claim",
                  misfire_grace_time=3600)
    log.info("领云贝已注册")

    # 点赞后取消（动态 + 歌曲）
    def do_like_unlike(c):
        # 随机点赞一首歌曲再取消
        import random
        songs = [167655, 1879860061, 2705043861]
        sid = random.choice(songs)
        like_and_unlike_song(c, sid)
        return {"已点赞并取消歌曲": sid}
    sched.add_job(task_wrapper("点赞后取消", do_like_unlike, notifier, client),
                  jitter_cron("40 12 * * *", jitter_min), id="like_unlike",
                  misfire_grace_time=3600)
    log.info("点赞后取消已注册")

    # 中间播放抽奖 + 音乐人任务
    sched.add_job(task_wrapper("中间播放抽奖", do_middle_play_lottery, notifier, client),
                  jitter_cron("10 11 * * *", jitter_min), id="lottery",
                  misfire_grace_time=3600)
    sched.add_job(task_wrapper("音乐人任务", run_musician_tasks, notifier, client),
                  jitter_cron("20 11 * * *", jitter_min), id="musician",
                  misfire_grace_time=3600)
    log.info("抽奖+音乐人任务已注册")

    # 每日汇总推送
    def send_daily_report():
        lines = [f"# 网易云日报 {date.today().isoformat()}", ""]
        for k, v in results.items():
            lines.append(f"- {k}: {v}")
        notifier.send("网易云日报", "\n".join(lines))
        results.clear()

    if notifier.enabled:
        report_cron = cfg.get("schedule", {}).get("report_cron", "30 10 * * *")
        sched.add_job(send_daily_report, jitter_cron(report_cron, 10),
                      id="report", misfire_grace_time=3600)
        log.info("日报推送已注册: cron≈%s", report_cron)

    if responder is not None:
        interval = int(reply_cfg.get("poll_interval", 60))
        sched.add_job(responder.poll_once,
                      IntervalTrigger(seconds=interval + random.randint(-10, 15)),
                      id="reply")
        log.info("私信回复已启用: 每 ~%ds", interval)

    keepalive_minutes = int(cfg.get("schedule", {}).get("keepalive_minutes", 30))
    sched.add_job(keepalive_ping, IntervalTrigger(minutes=keepalive_minutes),
                  args=[client], id="keepalive")
    log.info("保活: 每 %d 分钟", keepalive_minutes)

    log.info("全部任务启动，进入事件循环")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("收到退出信号")


if __name__ == "__main__":
    main()
