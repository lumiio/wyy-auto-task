"""HTTP 客户端：cookie、请求头、代理、风控码识别、熔断器注入。"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Mapping

import requests

from .antiban import AUTH_FAIL_CODES, RISK_CODES, CircuitBreaker, RiskControlError
from .crypto import eapi_payload, weapi_payload

log = logging.getLogger("ncm.client")

# 固定一套桌面 Chrome 头，不要每次请求都变，避免指纹漂移
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Referer": "https://music.163.com/",
    "Origin": "https://music.163.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "X-Requested-With": "XMLHttpRequest",
}

BASE_HOST = "https://music.163.com"


import uuid as _uuid

# 全局固定一个安卓设备指纹，避免每次请求都变导致风控
_DEVICE_ID = _uuid.uuid4().hex[:16]


class NCMClient:
    def __init__(
        self,
        cookie_str: str,
        ua: str = DEFAULT_UA,
        timeout: int = 15,
        proxy: str | None = None,
        breaker: CircuitBreaker | None = None,
    ):
        self.session = requests.Session()
        self.timeout = timeout
        self.breaker = breaker or CircuitBreaker()
        headers = dict(DEFAULT_HEADERS)
        headers["User-Agent"] = ua
        self.session.headers.update(headers)

        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            log.info("使用代理: %s", proxy)

        for part in cookie_str.split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            self.session.cookies.set(k.strip(), v.strip(), domain=".music.163.com")

        self.csrf = self.session.cookies.get("__csrf", "")

    # ---------- 风控判定 ----------
    def _inspect(self, data: dict, url: str) -> dict:
        code = data.get("code")
        if code in RISK_CODES:
            self.breaker.record_failure(f"{url} 返回风控码 {code}")
            raise RiskControlError(f"risk code {code} on {url}")
        if code in AUTH_FAIL_CODES:
            self.breaker.record_failure(f"{url} 登录态失效 code={code}")
            raise RuntimeError("cookie_expired")
        # 业务成功就复位
        self.breaker.record_success()
        return data

    # ---------- 底层请求 ----------
    def weapi_post(self, path: str, obj: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = weapi_payload(obj or {})
        if self.csrf:
            payload["csrf_token"] = self.csrf
        url = path if path.startswith("http") else BASE_HOST + path

        for attempt in range(3):
            try:
                r = self.session.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.timeout,
                )
                data = r.json()
                return self._inspect(data, url)
            except RiskControlError:
                raise
            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = min(30, 2 ** attempt + random.random() * 2)
                log.warning("weapi_post %s 第 %d 次失败: %s，%.1fs 后重试",
                            path, attempt + 1, e, wait)
                time.sleep(wait)
        self.breaker.record_failure(f"{url} 重试 3 次仍失败")
        raise RuntimeError(f"weapi_post {path} 重试 3 次仍失败")

    def plain_get(self, path: str, params: Mapping[str, str] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else BASE_HOST + path
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                data = r.json()
                return self._inspect(data, url)
            except RiskControlError:
                raise
            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = min(30, 2 ** attempt + random.random() * 2)
                log.warning("plain_get %s 第 %d 次失败: %s，%.1fs 后重试",
                            path, attempt + 1, e, wait)
                time.sleep(wait)
        self.breaker.record_failure(f"{url} GET 重试 3 次仍失败")
        raise RuntimeError(f"plain_get {path} 重试 3 次仍失败")

    def account_info(self) -> dict[str, Any]:
        return self.weapi_post("/weapi/nuser/account/get")

    def eapi_post(self, path: str, obj: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """POST 一个 eapi 接口。path 形如 /eapi/community/..."""
        url = path if path.startswith("http") else BASE_HOST + path
        body = dict(obj or {})
        # eapi 公共字段：设备指纹，发动态等敏感接口会校验
        body.setdefault("e_r", False)
        body.setdefault("header", "{}")
        body.setdefault("deviceId", _DEVICE_ID)
        body.setdefault("os", "android")
        payload = eapi_payload(url, body)
        for attempt in range(3):
            try:
                r = self.session.post(
                    url,
                    data=payload,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=self.timeout,
                )
                data = r.json()
                return self._inspect(data, url)
            except RiskControlError:
                raise
            except (requests.RequestException, json.JSONDecodeError) as e:
                wait = min(30, 2 ** attempt + random.random() * 2)
                log.warning("eapi_post %s 第 %d 次失败: %s", path, attempt + 1, e)
                time.sleep(wait)
        raise RuntimeError(f"eapi_post {path} 重试 3 次仍失败")
