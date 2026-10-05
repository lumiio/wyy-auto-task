"""网易云音乐 weapi/eapi 加密。"""
from __future__ import annotations

import base64
import hashlib
import json
import random
from typing import Any, Mapping
from urllib.parse import urlparse

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_IV = b"0102030405060708"
_PRESET_KEY = b"0CoJUm6Qyw8W8jud"
_BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# RSA-1024 公钥（PKCS#8 SubjectPublicKeyInfo），与官方客户端一致。
_PUBLIC_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDgtQn2JZ34ZC28NWYpAUd98iZ37BUrX/aKzmFbt7clFSs6sXqHauqKWqdtLkF2KexO40H1YTX8z2lSgBBOAxLsvaklV8k4cBFK9snQXE9/DDaFt6Rr7iVZMldczhC0JNgTz+SHXT6CBHuX3e9SdB1Ua44oncaTWz7OBGLbCiK45wIDAQAB\n"
    "-----END PUBLIC KEY-----\n"
)

# 延迟解析，避免 import 阶段开销
_RSA_N: int | None = None
_RSA_E: int | None = None


def _load_rsa() -> tuple[int, int]:
    global _RSA_N, _RSA_E
    if _RSA_N is None or _RSA_E is None:
        from Crypto.PublicKey import RSA

        key = RSA.import_key(_PUBLIC_KEY_PEM)
        _RSA_N, _RSA_E = int(key.n), int(key.e)
    return _RSA_N, _RSA_E


def _aes_cbc_b64(plaintext: str, key: bytes) -> str:
    cipher = AES.new(key, AES.MODE_CBC, _IV)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(ct).decode("ascii")


def _rsa_encrypt(hex_input: str) -> str:
    """no padding RSA：m^e mod n，输出 128 字节 hex。"""
    n, e = _load_rsa()
    m = int.from_bytes(hex_input.encode("utf-8"), "big")
    c = pow(m, e, n)
    return c.to_bytes(128, "big").hex()


def weapi_payload(obj: Mapping[str, Any] | str) -> dict[str, str]:
    """把 dict 包成 weapi 请求体 {"params": ..., "encSecKey": ...}。"""
    if not isinstance(obj, str):
        # separators 去掉空格，与 Go json.Marshal 行为对齐
        raw = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    else:
        raw = obj

    secret_key = "".join(random.choice(_BASE62) for _ in range(16))
    enc1 = _aes_cbc_b64(raw, _PRESET_KEY)
    params = _aes_cbc_b64(enc1, secret_key.encode("ascii"))
    enc_sec_key = _rsa_encrypt(secret_key[::-1])
    return {"params": params, "encSecKey": enc_sec_key}


# ---------- eapi（移动端接口） ----------
_EAPI_KEY = b"e82ckenh8dichen8"


def eapi_payload(full_url: str, obj: Mapping[str, Any] | str) -> dict[str, str]:
    """eapi 加密：AES-128-ECB，body 格式 url-xxx-data-xxx-md5。

    full_url 形如 https://music.163.com/eapi/community/...
    """
    if not isinstance(obj, str):
        data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    else:
        data = obj

    # url 里 /eapi 替换成 /api
    path = urlparse(full_url).path
    api_path = path.replace("/eapi/", "/api/", 1)

    digest = hashlib.md5(
        f"nobody{api_path}use{data}md5forencrypt".encode("utf-8")
    ).hexdigest()
    plaintext = f"{api_path}-36cd479b6b5-{data}-36cd479b6b5-{digest}"

    cipher = AES.new(_EAPI_KEY, AES.MODE_ECB)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return {"params": ct.hex().upper()}
