"""自动检查账号异常。"""
from __future__ import annotations

import logging

from .client import NCMClient

log = logging.getLogger("ncm.account_check")


def check_account(client: NCMClient) -> dict:
    """检查账号状态，返回异常列表。"""
    issues = []
    try:
        info = client.account_info()
        profile = info.get("profile") or {}
        level = profile.get("level")
        vip_type = info.get("vipType")
        if vip_type == 0:
            issues.append("VIP 已过期")
        log.info("账号: %s, 等级 %s, VIP %s", profile.get("nickname"), level, vip_type)
    except Exception as e:
        issues.append(f"账号信息获取失败: {e}")
        log.warning("账号检查失败: %s", e)
    return {"issues": issues}
