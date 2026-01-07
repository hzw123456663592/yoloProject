from __future__ import annotations
from fastapi import APIRouter

from common.settings import load_settings
from common.schemas import StreamStartRequest, StreamStartResponse
from media_api.services.zlm_client import ZLMediaKitClient
from media_api.services.stream_service import StreamService

router = APIRouter()
settings = load_settings()

_zlm = ZLMediaKitClient(
    base_url=settings.zlm["host"],
    secret=settings.zlm["secret"],
    vhost=settings.zlm["vhost"],
)

_stream_svc = StreamService(
    zlm=_zlm,
    public_host=settings.server["public_host"],
    webrtc_schema=settings.zlm.get("webrtc_schema", "webrtc"),
    app_default=settings.streams.get("default_app", "camera"),
)


@router.post("/streams/start", response_model=StreamStartResponse)
def start_stream(req: StreamStartRequest):
    data = _stream_svc.start_rtsp_to_webrtc(req.rtsp_url, camera_id=req.camera_id)
    return StreamStartResponse(**data)
