from __future__ import annotations
import requests
from typing import Any, Dict


class ZLMediaKitClient:
    def __init__(self, base_url: str, secret: str, vhost: str):
        self.base_url = base_url.rstrip("/")
        self.secret = secret
        self.vhost = vhost

    def add_stream_proxy(
        self,
        app: str,
        stream: str,
        rtsp_url: str,
        enable_webrtc: bool = True,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/index/api/addStreamProxy"
        params = {
            "secret": self.secret,
            "vhost": self.vhost,
            "app": app,
            "stream": stream,
            "url": rtsp_url,
            "enable_webrtc": 1 if enable_webrtc else 0,
            "enable_hls": 0,
            "enable_mp4": 0,
        }
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"ZLM error: {data}")
        return data
