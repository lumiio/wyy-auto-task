# 网易云音乐自动化脚本

自动刷歌、签到、乐迷团任务、VIP任务、云贝任务等。

## 功能

- 每日听歌 300 首 + 听歌时长 12 小时
- 每日签到（云贝 + VIP乐签）
- 乐迷团任务（播放、分享、点赞、评论、发笔记）
- VIP任务（黑胶乐签、一键领奖）
- 云贝任务（签到、浏览、访问商城）
- 自动关注歌手
- 新歌监控 + 自动推送
- 自动清理过期动态
- 自动领取云贝
- 账号异常检查
- 反风控熔断器

## 部署（宝塔面板）

1. 克隆仓库：
```bash
cd /www/wwwroot
git clone https://github.com/loliie-I/netease-bot.git
cd netease-bot
```

2. 安装依赖：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install requests pycryptodome PyYAML APScheduler
```

3. 配置：
```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入 cookie
```

4. 获取 cookie：
- 打开网易云音乐网页版
- F12 → Application → Cookies
- 复制 MUSIC_U 和 __csrf

5. 运行：
```bash
python bot/main.py
```

## 配置说明

编辑 config.yaml：

```yaml
cookie: "MUSIC_U=xxx; __csrf=xxx"
daily_songs: 300
daily_listen_minutes: 720
fansclub_group_id: "1567126346136354903"
follow_artist_id: 1050241
push_key: ""
```

## 定时任务（宝塔）

宝塔面板 → 计划任务 → 添加：

```bash
cd /www/wwwroot/netease-bot && .venv/bin/python bot/main.py
```

每天执行一次。

## 注意

- 不要频繁操作，避免封号
- 发笔记、关注用户等功能可能触发风控
- 养号 3-7 天后再开高级功能
