# 网易云音乐自动任务

网易云音乐每日自动签到、刷歌、乐迷团任务、VIP领奖、云贝任务等自动化脚本。

## 功能

### 每日任务
- 每日签到（安卓端 + Web端）
- 云贝签到 + 云贝任务
- 黑胶乐签 + VIP一键领奖
- 云小编任务（签到、领积分、抽奖）
- 云贝广告任务（每日10次×150云贝）
- 领云贝

### 乐迷团任务
- 自动获取所有已加入的乐迷团
- 播放歌曲任务
- 分享歌曲任务
- 点赞乐迷笔记（完成后自动取消点赞）
- 评论歌曲（完成后自动删评论）
- 发布图文笔记（完成后自动删除，可能被风控）

### 其他
- 新歌监控 + Server酱推送
- 自动关注歌手
- 私信自动回复
- 保活心跳
- 账号异常检查
- 点赞后自动取消
- 刷指定歌曲播放量
- 反风控熔断器

## 部署（宝塔面板）

1. 克隆仓库：
```bash
cd /www/wwwroot
git clone https://github.com/lumiio/wyy-auto-task.git
cd wyy-auto-task
```

2. 安装依赖：
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 配置：
```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml，填入 cookie 和 Server酱 key
```

4. 获取 cookie：
- 打开网易云音乐网页版 music.163.com
- F12 → Application → Cookies
- 复制 MUSIC_U 和 __csrf

5. 运行：
```bash
.venv/bin/python -m src.main
```

## 定时任务（宝塔）

宝塔面板 → 计划任务 → 添加 Shell 脚本：

```bash
cd /www/wwwroot/wyy-auto-task && .venv/bin/python -m src.main
```

建议设置为每天凌晨 0:00 执行。

## 配置说明

编辑 config.yaml：

```yaml
cookie: "MUSIC_U=xxx; __csrf=xxx"
server_chan_key: "SCTxxxx"  # Server酱推送key
```

## 注意

- 不要频繁操作，避免封号
- 发笔记、关注用户等功能可能触发风控
- 养号 3-7 天后再开高级功能
- 风控触发后会自动熔断，当天不再重试
