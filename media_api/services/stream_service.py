from __future__ import annotations
import uuid
from typing import Optional, Dict, Any

from media_api.services.zlm_client import ZLMediaKitClient


class StreamService:
    def __init__(self, zlm: ZLMediaKitClient, public_host: str, webrtc_schema: str, app_default: str):
        self.zlm = zlm
        self.public_host = public_host
        self.webrtc_schema = webrtc_schema
        self.app_default = app_default

    def start_rtsp_to_webrtc(self, rtsp_url: str, camera_id: Optional[str] = None) -> Dict[str, Any]:
        app = self.app_default
        stream_id = uuid.uuid4().hex[:8]
        cid = camera_id or stream_id

        self.zlm.add_stream_proxy(app=app, stream=stream_id, rtsp_url=rtsp_url, enable_webrtc=True)

        # 不同 ZLM/网关的 webrtc url 可能有差异，这里统一封装
        webrtc_url = f"{self.webrtc_schema}://{self.public_host}/{app}/{stream_id}"

        return {
            "app": app,
            "stream": stream_id,
            "webrtc_url": webrtc_url,
            "rtsp_url": rtsp_url,
            "camera_id": cid,
        }
